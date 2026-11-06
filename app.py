import logging
import re
import sqlite3
import threading
import time
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from config import Config
from email_service import send_receipt_email
from models import (
    add_product,
    add_to_cart,
    clear_cart,
    create_customer,
    create_transaction,
    delete_product,
    get_all_customers,
    get_all_products,
    get_all_transactions,
    get_cart_items,
    get_cart_summary,
    get_customer_by_email,
    get_customer_by_id,
    get_customer_transactions,
    get_db,
    get_product_by_id,
    get_product_by_rfid,
    get_transaction_by_id,
    get_transaction_items,
    get_transaction_stats,
    init_db,
    remove_from_cart,
    update_product,
    verify_customer_password,
)
from serial_comm import SerialCommunicator

from dotenv import load_dotenv
load_dotenv()

# Configure application logging (both console and file)
import os
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.log')
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(log_file, encoding='utf-8')],
    force=True
)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('serial_comm').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Initialize database schema immediately
try:
    init_db()
    logger.info("Database initialized successfully at startup.")
except Exception as e:
    logger.error("Failed to initialize database at startup: %s", e)

# Initialize Flask application and configuration
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# Application database initialization state
_db_initialized = True


@app.before_request
def initialize_database():
    """Ensures database schema and sample data exist."""
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True
        logger.info("Database initialized on request.")


# Instantiate Serial Communicator for hardware communication
serial_comm = SerialCommunicator(app=app)

# Start serial communicator background thread only if not in demo mode
if not Config.DEMO_MODE:
    serial_comm.start()
    logger.info("Serial communication started in background thread.")
else:
    logger.info("Demo Mode active: Serial communication hardware thread disabled.")

# Shared global state
last_scan_time = {}  # Format: {rfid_uid: float_timestamp}
weight_data = {
    'current': 0.0,
    'measured': 0.0,
    'expected': 0.0,
    'status': 'waiting',
    'message': 'Waiting for RFID scan.'
}
# Monotonic timestamp of the most recent accepted RFID scan.
# The scale is given a short settling period before comparison.
last_scan_at = None
WEIGHT_CHECK_DELAY = 3.0  # seconds after scan before checking weight

trolley_status = 'disconnected'
recent_scans = []  # List of dicts: {product_name, product_price, rfid_uid, timestamp, customer_id}
_checkout_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Authentication Decorators
# ---------------------------------------------------------------------------

def login_required(f):
    """Restricts access to authenticated customers. Redirects unauthenticated users to login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('customer_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Restricts access to authenticated administrators. Redirects unauthenticated users to login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# Internal Helper Functions
# ---------------------------------------------------------------------------

_last_hw_led = None
_last_weight_status = 'waiting'
_hardware_error_until = 0.0


def _send_hardware_command(command):
    """Send one command to the Arduino; serial_comm owns the serial port."""
    try:
        sender = getattr(serial_comm, 'send_command', None)
        return bool(sender(command)) if callable(sender) else False
    except Exception as exc:
        logger.warning("Hardware command failed: %s", exc)
        return False


def _set_hardware_led(state):
    """Set exactly one status LED. Avoid retransmitting the same state."""
    global _last_hw_led
    state = str(state).lower()
    if state not in {'red', 'green', 'yellow', 'off'}:
        return False
    if state == _last_hw_led:
        return True
    sent = _send_hardware_command({"command": "led", "state": state})
    if sent:
        _last_hw_led = state
    return sent


def _signal_hardware_error():
    """Show an error and request a short buzzer pattern once per error event."""
    global _last_weight_status, _hardware_error_until
    _hardware_error_until = time.monotonic() + 3.0
    _set_hardware_led('red')
    if _last_weight_status != 'mismatch':
        _send_hardware_command({"command": "buzzer", "action": "beep", "count": 3})
    _last_weight_status = 'mismatch'


def _evaluate_weight():
    """Compare total scale reading with total expected cart weight."""
    global weight_data, last_scan_at, _last_weight_status, _hardware_error_until

    expected = float(weight_data.get('expected', 0.0) or 0.0)
    measured = float(weight_data.get('current', 0.0) or 0.0)

    if expected <= 0:
        if time.monotonic() < _hardware_error_until:
            weight_data['status'] = 'mismatch'
            weight_data['message'] = 'Hardware or RFID error. Please check and retry.'
            _set_hardware_led('red')
            return 'mismatch'
        weight_data['status'] = 'waiting'
        weight_data['message'] = 'Waiting for RFID scan.'
        # Keep green after a completed successful checkout until the next scan.
        if _last_weight_status != 'verified':
            _last_weight_status = 'waiting'
            _set_hardware_led('off')
        return 'waiting'

    if last_scan_at is None or (time.monotonic() - last_scan_at) < WEIGHT_CHECK_DELAY:
        weight_data['status'] = 'checking'
        weight_data['message'] = 'Place the scanned item on the trolley scale.'
        _last_weight_status = 'checking'
        _set_hardware_led('yellow')
        return 'checking'

    tolerance = float(getattr(Config, 'WEIGHT_TOLERANCE', 10.0))
    difference = abs(measured - expected)

    # A negative value is a sensor/calibration fault, not a valid weight.
    if measured < 0 or difference > tolerance:
        weight_data['status'] = 'mismatch'
        if measured < 0:
            weight_data['message'] = (
                f'Negative scale reading ({measured:.2f} g). Check HX711 calibration and wiring.'
            )
        else:
            weight_data['message'] = (
                f'Weight mismatch! Expected: {expected:.2f} g, Measured: {measured:.2f} g'
            )
        _signal_hardware_error()
    else:
        weight_data['status'] = 'verified'
        weight_data['message'] = 'Weight verified successfully.'
        _set_hardware_led('green')
        _last_weight_status = 'verified'

    return weight_data['status']


def _handle_scan(uid, customer_id=None):
    """
    Core business logic for handling RFID scans:
    1. Check duplicate cooldown
    2. Lookup product by RFID
    3. Verify product existence
    4. Add to cart
    5. Update scan cooldown timestamp
    6. Record scan in recent scans list (max 10 per customer)
    7. Update expected weight
    8. Return JSON payload
    """
    global weight_data, recent_scans, last_scan_time, last_scan_at, _last_weight_status

    uid = str(uid).strip()
    now = time.time()

    # 1. Check duplicate: if scanned within SCAN_COOLDOWN seconds
    if uid in last_scan_time and (now - last_scan_time[uid]) < Config.SCAN_COOLDOWN:
        _signal_hardware_error()
        return jsonify({
            'success': False,
            'status': 'error',
            'message': 'Duplicate scan'
        }), 400

    # 2. Look up product by RFID UID
    product = get_product_by_rfid(uid)

    # 3. If not found, return error
    if not product:
        _signal_hardware_error()
        return jsonify({
            'success': False,
            'status': 'error',
            'message': 'Unknown product'
        }), 404

    # Resolve customer ID (from active session or first registered customer fallback)
    if not customer_id:
        customer_id = session.get('customer_id')
    if not customer_id:
        all_customers = get_all_customers()
        if all_customers:
            customer_id = all_customers[0]['id']
        else:
            _signal_hardware_error()
            return jsonify({
                'success': False,
                'status': 'error',
                'message': 'No customer available for cart association'
            }), 400

    # 4. Add product to customer cart
    add_to_cart(customer_id, product['id'], quantity=1)

    # 5. Update last scan timestamp
    last_scan_time[uid] = now

    # 6. Add to recent_scans list (prepend, keep max 10 per customer)
    timestamp_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    time_display = datetime.now().strftime('%I:%M:%S %p')
    scan_entry = {
        'product_name': product['name'],
        'name': product['name'],
        'product_price': float(product['price']),
        'price': float(product['price']),
        'rfid_uid': uid,
        'timestamp': timestamp_iso,
        'time': time_display,
        'customer_id': customer_id
    }
    recent_scans.insert(0, scan_entry)

    # Maintain maximum of 10 recent scans for this customer
    customer_scans = [s for s in recent_scans if s.get('customer_id') == customer_id]
    if len(customer_scans) > 10:
        for excess_scan in customer_scans[10:]:
            if excess_scan in recent_scans:
                recent_scans.remove(excess_scan)

    # 7. Update expected weight and begin a new item-verification cycle.
    product_weight = float(product.get('weight', 0.0) or 0.0)
    weight_data['expected'] = round(
        float(weight_data.get('expected', 0.0)) + product_weight, 2
    )
    last_scan_at = time.monotonic()
    weight_data['status'] = 'checking'
    weight_data['message'] = 'Item scanned. Place it on the trolley scale.'
    _last_weight_status = 'checking'
    _set_hardware_led('yellow')
    # Open the gate and show the actual database product details on the OLED.
    servo_sent = _send_hardware_command({"command": "servo", "action": "open"})
    display_sent = _send_hardware_command({
        "command": "display",
        "name": str(product.get('name', 'Product')),
        "weight": product_weight,
        "price": float(product.get('price', 0.0) or 0.0)
    })
    if not servo_sent:
        logger.warning("Servo open command could not be sent to Arduino")
    if not display_sent:
        logger.warning("Product display command could not be sent to Arduino")

    logger.info(
        "RFID product added: %s; product weight=%.2f g; expected total=%.2f g",
        product['name'], product_weight, weight_data['expected']
    )

    # 8. Return success response
    return jsonify({
        'success': True,
        'status': 'success',
        'message': f"Added '{product['name']}' to cart",
        'product': product,
        'weight_status': weight_data,
        'weight_data': weight_data
    })


def _handle_weight(value):
    """Store a scale reading and update the hardware/dashboard verification state."""
    global weight_data

    try:
        val_float = float(value)
    except (ValueError, TypeError):
        return jsonify({
            'success': False,
            'status': 'error',
            'message': 'Invalid weight measurement format'
        }), 400

    if not (float('-inf') < val_float < float('inf')):
        return jsonify({
            'success': False,
            'status': 'error',
            'message': 'Weight measurement must be a finite number'
        }), 400

    weight_data['current'] = round(val_float, 2)
    weight_data['measured'] = weight_data['current']

    result = _evaluate_weight()

    return jsonify({
        'success': True,
        'status': result,
        'message': weight_data['message'],
        'weight_status': weight_data,
        'data': weight_data
    })


# ---------------------------------------------------------------------------
# Authentication Routes
# ---------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles both customer and administrator login."""
    if request.method == 'POST':
        email_or_user = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        is_admin_check = bool(request.form.get('is_admin'))

        # Input handling validations
        if not email_or_user:
            flash('Please enter your email or admin username.', 'error')
            return render_template('login.html', email_value=email_or_user, is_admin=is_admin_check)

        if not password:
            flash('Please enter your password.', 'error')
            return render_template('login.html', email_value=email_or_user, is_admin=is_admin_check)

        if is_admin_check:
            # Validate administrator credentials against Config
            if ((email_or_user == Config.ADMIN_USERNAME or email_or_user.lower() == Config.ADMIN_EMAIL.lower())
                    and password == Config.ADMIN_PASSWORD):
                session.clear()
                session['is_admin'] = True
                session['admin_username'] = Config.ADMIN_USERNAME
                flash('Logged in successfully as Administrator.', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid administrator credentials. Please check your username and password.', 'error')
                return render_template('login.html', email_value=email_or_user, is_admin=True)
        else:
            # Validate customer credentials against database
            customer = get_customer_by_email(email_or_user)
            if not customer:
                flash('No account found with this email address.', 'error')
                return render_template('login.html', email_value=email_or_user, is_admin=False)

            if verify_customer_password(customer['password'], password):
                session.clear()
                session['customer_id'] = customer['id']
                session['customer_name'] = customer['name']
                session['customer_email'] = customer['email']
                flash(f"Welcome back, {customer['name']}!", 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Incorrect password. Please try again.', 'error')
                return render_template('login.html', email_value=email_or_user, is_admin=False)

    # If user is already logged in, redirect to respective dashboard
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    if session.get('customer_id'):
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handles new customer account registration with distinct validations and specific error handling."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        form_data = {
            'name': name,
            'email': email,
            'phone': phone
        }

        # 1. Name validation
        if not name:
            flash('Full name is required.', 'error')
            return render_template('register.html', form_data=form_data)
        elif len(name) < 2:
            flash('Full name must be at least 2 characters long.', 'error')
            return render_template('register.html', form_data=form_data)

        # 2. Email validation
        if not email:
            flash('Email address is required.', 'error')
            return render_template('register.html', form_data=form_data)
        elif not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
            flash('Please enter a valid email address (e.g. name@example.com).', 'error')
            return render_template('register.html', form_data=form_data)

        # 3. Optional Phone validation
        if phone:
            clean_phone = re.sub(r'[\s\-+()]', '', phone)
            if not clean_phone.isdigit() or len(clean_phone) < 10 or len(clean_phone) > 15:
                flash('Please enter a valid phone number (10 to 15 digits).', 'error')
                return render_template('register.html', form_data=form_data)

        # 4. Password validation
        if not password:
            flash('Password is required.', 'error')
            return render_template('register.html', form_data=form_data)
        elif len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('register.html', form_data=form_data)

        # 5. Confirm Password validation
        if not confirm_password:
            flash('Please confirm your password.', 'error')
            return render_template('register.html', form_data=form_data)
        elif password != confirm_password:
            flash('Passwords do not match. Please verify and re-type.', 'error')
            return render_template('register.html', form_data=form_data)

        # 6. Check existing email
        existing_customer = get_customer_by_email(email)
        if existing_customer:
            flash('An account with this email address already exists. Please log in.', 'error')
            return render_template('register.html', form_data=form_data)

        # 7. Create Customer
        try:
            create_customer(name=name, email=email, password=password, phone=phone if phone else None)
            flash('Account created successfully! Please log in with your credentials.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError as e:
            logger.warning("Integrity error during registration for %s: %s", email, e)
            flash('An account with this email address already exists. Please log in.', 'error')
            return render_template('register.html', form_data=form_data)
        except Exception as e:
            logger.exception("Registration error: %s", e)
            err_msg = str(e)
            if 'unique' in err_msg.lower() or 'integrity' in err_msg.lower():
                flash('An account with this email address already exists.', 'error')
            elif 'locked' in err_msg.lower():
                flash('Database is temporarily busy. Please try again.', 'error')
            else:
                flash(f'Registration could not be completed ({err_msg}). Please try again.', 'error')
            return render_template('register.html', form_data=form_data)

    return render_template('register.html', form_data={})


@app.route('/logout', methods=['GET'])
def logout():
    """Clears user session and redirects to the login screen."""
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# Customer Pages
# ---------------------------------------------------------------------------

@app.route('/', methods=['GET'])
def index():
    """Entry point: redirects authenticated users to their dashboard, otherwise to login."""
    if session.get('customer_id'):
        return redirect(url_for('dashboard'))
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))


@app.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    """Renders customer shopping dashboard."""
    customer = get_customer_by_id(session['customer_id'])
    products = get_all_products()
    return render_template(
        'customer_dashboard.html',
        customer=customer,
        products=products,
        demo_mode=Config.DEMO_MODE
    )


@app.route('/cart', methods=['GET'])
@login_required
def cart():
    """Renders customer cart and checkout page."""
    customer = get_customer_by_id(session['customer_id'])
    return render_template('cart.html', customer=customer)


# ---------------------------------------------------------------------------
# Customer API
# ---------------------------------------------------------------------------

@app.route('/api/dashboard-data', methods=['GET'])
@login_required
def api_dashboard_data():
    """Returns real-time dashboard data including cart summary, scans, weight status, and trolley state."""
    customer_id = session['customer_id']
    summary = get_cart_summary(customer_id)
    cust_scans = [s for s in recent_scans if s.get('customer_id') == customer_id][:10]

    current_trolley_status = trolley_status
    if not Config.DEMO_MODE and serial_comm and serial_comm.is_connected():
        current_trolley_status = 'connected'

    return jsonify({
        'success': True,
        'status': 'success',
        'cart_summary': summary,
        'total_products': summary['total_items'],
        'total_weight': summary['total_weight'],
        'current_bill': summary['total_price'],
        'recent_scans': cust_scans,
        'weight_status': {
            'current': weight_data['current'],
            'measured': weight_data['current'],
            'expected': weight_data['expected'],
            'status': weight_data['status'],
            'message': weight_data['message']
        },
        'trolley_status': current_trolley_status,
        'demo_mode': Config.DEMO_MODE
    })


@app.route('/api/cart', methods=['GET'])
@login_required
def api_cart():
    """Returns all items in the customer's cart alongside calculation summary."""
    customer_id = session['customer_id']
    items = get_cart_items(customer_id)
    summary = get_cart_summary(customer_id)

    return jsonify({
        'success': True,
        'status': 'success',
        'items': items,
        'cart_items': items,
        'cart_summary': summary,
        'total': summary['total_price'],
        'total_amount': summary['total_price'],
        'total_items': summary['total_items'],
        'total_weight': summary['total_weight']
    })


@app.route('/api/cart/remove', methods=['POST'])
@login_required
def api_cart_remove():
    """Removes a product from the shopping cart and updates expected weight."""
    customer_id = session['customer_id']
    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')

    if not product_id and data.get('rfid_uid'):
        prod = get_product_by_rfid(data.get('rfid_uid'))
        if prod:
            product_id = prod['id']

    if not product_id:
        return jsonify({'success': False, 'status': 'error', 'message': 'Product ID is required'}), 400

    try:
        product_id = int(product_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'status': 'error', 'message': 'Invalid Product ID'}), 400

    remove_from_cart(customer_id, product_id)

    # Sync expected weight with updated cart and re-check the scale.
    global last_scan_at, _last_weight_status
    summary = get_cart_summary(customer_id)
    weight_data['expected'] = float(summary['total_weight'] or 0.0)
    last_scan_at = time.monotonic()
    _last_weight_status = 'checking' if weight_data['expected'] > 0 else 'waiting'
    weight_data['status'] = 'checking' if weight_data['expected'] > 0 else 'waiting'
    weight_data['message'] = 'Cart changed. Rechecking trolley weight.'
    _set_hardware_led('yellow' if weight_data['expected'] > 0 else 'off')

    return jsonify({
        'success': True,
        'status': 'success',
        'message': 'Product removed from cart',
        'cart_summary': summary,
        'weight_status': weight_data
    })


@app.route('/api/scan', methods=['POST'])
def api_scan():
    """
    Handles RFID scans received from hardware or test requests.
    Expects JSON: { "uid": string }
    """
    data = request.get_json(silent=True) or {}
    uid = data.get('uid') or data.get('rfid_uid')

    if not uid:
        return jsonify({'success': False, 'status': 'error', 'message': 'RFID UID is required'}), 400

    customer_id = session.get('customer_id') or data.get('customer_id')
    return _handle_scan(uid, customer_id=customer_id)


@app.route('/api/weight', methods=['POST'])
def api_weight():
    """
    Handles weight measurements received from hardware.
    Expects JSON: { "value": float }
    """
    data = request.get_json(silent=True) or {}
    val = data.get('value')
    if val is None:
        val = data.get('weight')

    if val is None:
        return jsonify({'success': False, 'status': 'error', 'message': 'Weight value is required'}), 400

    return _handle_weight(val)


@app.route('/api/checkout', methods=['POST'])
@login_required
def api_checkout():
    """
    Processes final cart checkout:
    1. Checks cart contents under lock
    2. Creates transaction record
    3. Clears active cart immediately (prevents duplicate orders)
    4. Resets weight scale state & recent scans
    5. Sends email receipt
    """
    global last_scan_at, _last_weight_status
    customer_id = session['customer_id']
    data = request.get_json(silent=True) or {}
    payment_method = data.get('payment_method', 'Cash')
    if isinstance(payment_method, str) and payment_method.lower() == 'cash':
        payment_method = 'Cash'

    with _checkout_lock:
        cart_items = get_cart_items(customer_id)
        if not cart_items:
            return jsonify({
                'success': False,
                'status': 'error',
                'message': 'Cannot complete checkout: Cart is empty'
            }), 400

        # Yellow LED indicates payment/checkout is in progress.
        _set_hardware_led('yellow')

        # Build transaction line items
        items = []
        for item in cart_items:
            items.append({
                'product_id': item['product_id'],
                'product_name': item['name'],
                'name': item['name'],
                'quantity': item['quantity'],
                'qty': item['quantity'],
                'unit_price': item['price'],
                'price': item['price'],
                'subtotal': item['subtotal']
            })

        summary = get_cart_summary(customer_id)
        total_amount = summary['total_price']

        # Create transaction with exact current timestamp
        transaction_id = create_transaction(
            customer_id=customer_id,
            total_amount=total_amount,
            payment_method=payment_method,
            items=items
        )

        # Clear customer cart immediately inside lock to prevent race conditions
        clear_cart(customer_id)

        # Reset shared weight tracking and recent scans for this customer
        weight_data['current'] = 0.0
        weight_data['measured'] = 0.0
        weight_data['expected'] = 0.0
        weight_data['status'] = 'waiting'
        weight_data['message'] = 'Payment completed. Ready for next customer.'
        last_scan_at = None
        _last_weight_status = 'waiting'
        recent_scans[:] = [s for s in recent_scans if s.get('customer_id') != customer_id]

    # Attempt sending receipt email outside lock (so email timeout does not block checkout)
    customer = get_customer_by_id(customer_id)
    email_sent = False
    if customer and customer.get('email'):
        try:
            email_sent = send_receipt_email(
                customer_email=customer['email'],
                customer_name=customer.get('name', 'Valued Customer'),
                transaction_id=transaction_id,
                items=items,
                total_amount=total_amount
            )
        except Exception as e:
            logger.error("Failed to send receipt email: %s", e)
            email_sent = False

    _set_hardware_led('green')
    _last_weight_status = 'verified'

    return jsonify({
        'success': True,
        'status': 'success',
        'message': 'Checkout completed successfully',
        'transaction_id': transaction_id,
        'total': total_amount,
        'email_sent': bool(email_sent)
    })


# ---------------------------------------------------------------------------
# Demo API
# ---------------------------------------------------------------------------

@app.route('/api/demo/scan', methods=['POST'])
@login_required
def api_demo_scan():
    """Simulation endpoint for RFID scanning in Demo Mode."""
    data = request.get_json(silent=True) or {}
    uid = data.get('rfid_uid') or data.get('uid')

    if not uid:
        return jsonify({'success': False, 'status': 'error', 'message': 'RFID UID is required'}), 400

    return _handle_scan(uid, customer_id=session['customer_id'])


@app.route('/api/demo/weight', methods=['POST'])
@login_required
def api_demo_weight():
    """Simulation endpoint for weight scale in Demo Mode."""
    data = request.get_json(silent=True) or {}
    val = data.get('value')
    if val is None:
        val = data.get('weight')

    if val is None:
        return jsonify({'success': False, 'status': 'error', 'message': 'Weight value is required'}), 400

    return _handle_weight(val)


# ---------------------------------------------------------------------------
# Admin Pages & Endpoints
# ---------------------------------------------------------------------------

@app.route('/admin', methods=['GET'])
@admin_required
def admin_dashboard():
    """Renders administrative dashboard with business statistics."""
    stats = get_transaction_stats()
    all_transactions = get_all_transactions()
    recent_transactions = all_transactions[:5]
    return render_template(
        'admin_dashboard.html',
        stats=stats,
        transactions=recent_transactions
    )


@app.route('/admin/products', methods=['GET'])
@admin_required
def admin_products():
    """Renders product catalog management page."""
    products = get_all_products()
    return render_template('admin_products.html', products=products)


@app.route('/admin/products/add', methods=['POST'])
@admin_required
def admin_products_add():
    """Adds a new product to the catalog."""
    name = request.form.get('name', '').strip()
    rfid_uid = request.form.get('rfid_uid', '').strip().upper()
    price = request.form.get('price', '0')
    category = request.form.get('category', '').strip()
    weight = request.form.get('weight', '0')

    if not name or not rfid_uid or not price:
        flash('Product name, RFID UID, and price are required fields.', 'error')
        return redirect(url_for('admin_products'))

    try:
        price_val = float(price)
        weight_val = float(weight) if weight else 0.0
    except ValueError:
        flash('Price and weight must be valid numeric values.', 'error')
        return redirect(url_for('admin_products'))

    existing = get_product_by_rfid(rfid_uid)
    if existing:
        flash(f"A product with RFID UID '{rfid_uid}' already exists.", 'error')
        return redirect(url_for('admin_products'))

    try:
        add_product(name=name, rfid_uid=rfid_uid, price=price_val, category=category, weight=weight_val)
        flash(f"Product '{name}' added successfully!", 'success')
    except Exception as e:
        logger.error("Error adding product: %s", e)
        flash(f"Error adding product: {e}", 'error')

    return redirect(url_for('admin_products'))


@app.route('/admin/products/update/<int:id>', methods=['POST'])
@admin_required
def admin_products_update(id):
    """Updates an existing product in the catalog."""
    name = request.form.get('name', '').strip()
    rfid_uid = request.form.get('rfid_uid', '').strip().upper()
    price = request.form.get('price', '0')
    category = request.form.get('category', '').strip()
    weight = request.form.get('weight', '0')

    if not name or not rfid_uid or not price:
        flash('Product name, RFID UID, and price are required fields.', 'error')
        return redirect(url_for('admin_products'))

    try:
        price_val = float(price)
        weight_val = float(weight) if weight else 0.0
    except ValueError:
        flash('Price and weight must be valid numeric values.', 'error')
        return redirect(url_for('admin_products'))

    existing = get_product_by_rfid(rfid_uid)
    if existing and existing['id'] != id:
        flash(f"RFID UID '{rfid_uid}' is already assigned to another product.", 'error')
        return redirect(url_for('admin_products'))

    try:
        update_product(
            product_id=id,
            name=name,
            rfid_uid=rfid_uid,
            price=price_val,
            category=category,
            weight=weight_val
        )
        flash(f"Product '{name}' updated successfully!", 'success')
    except Exception as e:
        logger.error("Error updating product %d: %s", id, e)
        flash(f"Error updating product: {e}", 'error')

    return redirect(url_for('admin_products'))


@app.route('/admin/products/delete/<int:id>', methods=['POST'])
@admin_required
def admin_products_delete(id):
    """Deletes a product from the catalog."""
    try:
        delete_product(id)
        flash('Product deleted successfully.', 'success')
    except Exception as e:
        logger.error("Error deleting product %d: %s", id, e)
        flash(f"Error deleting product: {e}", 'error')

    return redirect(url_for('admin_products'))


@app.route('/admin/customers', methods=['GET'])
@admin_required
def admin_customers():
    """Renders customer accounts directory."""
    customers = get_all_customers()
    return render_template('admin_customers.html', customers=customers)


@app.route('/admin/transactions', methods=['GET'])
@admin_required
def admin_transactions():
    """Renders transaction history listing."""
    transactions = get_all_transactions()
    return render_template('admin_transactions.html', transactions=transactions)


@app.route('/admin/transactions/<int:id>/items', methods=['GET'])
@admin_required
def admin_transaction_items(id):
    """Returns items breakdown for a specific transaction in JSON format."""
    transaction = get_transaction_by_id(id)
    items = get_transaction_items(id)
    return jsonify({
        'success': True,
        'status': 'success',
        'transaction_id': id,
        'transaction': transaction,
        'items': items
    })


# ---------------------------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print(f"Smart Trolley server running on port {Config.PORT}")
    app.run(
        host='0.0.0.0',
        port=Config.PORT,
        debug=False,
        use_reloader=False,
        threaded=True
    )