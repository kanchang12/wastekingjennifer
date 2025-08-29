import os
import re
import json
import requests
import traceback
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from openai import OpenAI
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from flask_cors import CORS
import logging

# Disable Flask HTTP request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# API Integration
try:
    from utils.wasteking_api import complete_booking, create_booking, get_pricing, create_payment_link
    API_AVAILABLE = True
    print("API AVAILABLE")
except ImportError:
    API_AVAILABLE = False
    print("API NOT AVAILABLE - using fallback")

# SMS sender
def send_sms(phone, message):
    try:
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        from_number = os.getenv('TWILIO_PHONE_NUMBER', '+447700900000')
        
        if not account_sid or not auth_token:
            print(f"SMS FALLBACK: Would send to {phone}: {message}")
            return True
            
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        client.messages.create(body=message, from_=from_number, to=phone)
        print(f"SMS SENT to {phone}")
        return True
        
    except ImportError:
        print(f"SMS FALLBACK: Would send to {phone}: {message}")
        return True
    except Exception as e:
        print(f"SMS ERROR: {e}")
        return False

# Email sender
def send_email(subject, body, recipient='kanchan.g12@gmail.com'):
    try:
        email_address = os.getenv('WASTEKING_EMAIL')
        email_password = os.getenv('WASTEKING_EMAIL_PASSWORD')
        
        if not email_address or not email_password:
            print(f"EMAIL FALLBACK: {subject}")
            return True
            
        msg = MIMEMultipart()
        msg['From'] = email_address
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('mail.wasteking.co.uk', 587)
        server.starttls()
        server.login(email_address, email_password)
        server.sendmail(email_address, recipient, msg.as_string())
        server.quit()
        
        print(f"EMAIL SENT: {subject}")
        return True
    except Exception as e:
        print(f"EMAIL ERROR: {e}")
        return False

class WasteKingAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.conversations = {}
        
    def process_message(self, message, conversation_id):
        print(f"\nCustomer [{conversation_id[-6:]}]: {message}")
        
        state = self.conversations.get(conversation_id, {
            'stage': 'start',
            'customer_data': {},
            'history': [],
            'service_type': None,
            'customer_type': None,
            'data_collected': []
        })
        
        state['history'].append(f"Customer: {message}")
        response = self.route_message(message, state)
        state['history'].append(f"Agent: {response}")
        self.conversations[conversation_id] = state
        
        print(f"Agent [{conversation_id[-6:]}]: {response}")
        return response, state.get('stage', 'conversation')
    
    def route_message(self, message, state):
        msg_lower = message.lower()
        
        # 1. Customer type detection
        if not state.get('customer_type'):
            if any(word in msg_lower for word in ['trade', 'business', 'commercial', 'company']):
                state['customer_type'] = 'trade'
                print(f"CUSTOMER TYPE: trade")
            elif any(word in msg_lower for word in ['domestic', 'home', 'house', 'personal']):
                state['customer_type'] = 'domestic'
                print(f"CUSTOMER TYPE: domestic")
            else:
                return "Are you a domestic or trade customer?"
        
        # 2. Service detection
        if not state.get('service_type'):
            service = self.detect_service(msg_lower)
            if service:
                state['service_type'] = service
                print(f"SERVICE DETECTED: {service}")
        
        # 3. Route to appropriate handler
        service = state.get('service_type')
        
        if service == 'skip_hire':
            return self.handle_skip_hire(message, state, msg_lower)
        elif service == 'mav':
            return self.handle_mav(message, state, msg_lower)
        elif service == 'grab':
            return self.handle_grab(message, state, msg_lower)
        elif service == 'skip_collection':
            return self.handle_skip_collection(message, state, msg_lower)
        elif service in ['toilet_hire', 'asbestos', 'road_sweep', 'hazardous']:
            return self.handle_specialist(message, state, msg_lower, service)
        else:
            return self.handle_general(message, state, msg_lower)
    
    def detect_service(self, msg_lower):
        if any(word in msg_lower for word in ['skip']) and not any(word in msg_lower for word in ['collection', 'collect']):
            return 'skip_hire'
        elif any(phrase in msg_lower for phrase in ['skip collection', 'collect skip', 'pick up skip']):
            return 'skip_collection'
        elif any(phrase in msg_lower for phrase in ['man and van', 'clearance', 'house clearance', 'office clearance']):
            return 'mav'
        elif any(word in msg_lower for word in ['grab', 'wheeler']):
            return 'grab'
        elif 'toilet' in msg_lower or 'portaloo' in msg_lower:
            return 'toilet_hire'
        elif 'asbestos' in msg_lower:
            return 'asbestos'
        elif any(phrase in msg_lower for phrase in ['road sweep', 'street sweep']):
            return 'road_sweep'
        elif 'hazardous' in msg_lower:
            return 'hazardous'
        return None
    
    # SKIP HIRE - AUTO BOOK IMMEDIATELY
    def handle_skip_hire(self, message, state, msg_lower):
        print("PROCESSING SKIP HIRE")
        
        # Extract all data
        self.extract_basic_data(message, state)
        
        # Required fields
        required = ['name', 'phone', 'postcode']
        for field in required:
            if not state['customer_data'].get(field):
                if field == 'name':
                    return "What's your name?"
                elif field == 'phone':
                    return "What's your phone number?"
                elif field == 'postcode':
                    return "What's your postcode?"
        
        # All required data collected - AUTO BOOK IMMEDIATELY
        if not state.get('booking_completed'):
            return self.auto_book_skip(state)
        
        return "Your skip booking is being processed."
    

Action: Schedule delivery within 24 hours
"""
        send_email(subject, body, 'operations@wasteking.co.uk')
        
        state['booking_completed'] = True
        state['stage'] = 'completed'
        
        print(f"FALLBACK BOOKING COMPLETED: {booking_ref} - {price}")
        vat_note = " (+ VAT)" if state.get('customer_type') == 'trade' else ""
        return f"Perfect! Your {skip_size} skip is booked for {postcode} at {price}{vat_note}. Reference: {booking_ref}. You'll receive SMS confirmation shortly. Delivery within 24 hours."
    
    def get_fallback_price(self, postcode, skip_size):
        pricing = {
            'london': {'4yd': '£190', '6yd': '£230', '8yd': '£270', '12yd': '£370'},
            'midlands': {'4yd': '£170', '6yd': '£210', '8yd': '£250', '12yd': '£350'},  
            'north': {'4yd': '£160', '6yd': '£200', '8yd': '£240', '12yd': '£340'},
            'default': {'4yd': '£180', '6yd': '£220', '8yd': '£260', '12yd': '£360'}
        }
        
        postcode_upper = postcode.upper()
        if any(postcode_upper.startswith(p) for p in ['E', 'W', 'N', 'S', 'EC', 'WC']):
            region = 'london'
        elif any(postcode_upper.startswith(p) for p in ['B', 'CV', 'WS', 'WV']):
            region = 'midlands'
        elif any(postcode_upper.startswith(p) for p in ['M', 'L', 'S', 'LS']):
            region = 'north'
        else:
            region = 'default'
        
        return pricing[region].get(skip_size, pricing[region]['8yd'])
    
    # MAN & VAN - COMPLETE DATA COLLECTION FIRST
    def handle_mav(self, message, state, msg_lower):
        print("PROCESSING MAN & VAN")
        
        # Extract all data first
        self.extract_basic_data(message, state)
        self.extract_mav_data(message, state, msg_lower)
        
        # Heavy materials check
        if any(material in msg_lower for material in ['soil', 'rubble', 'concrete', 'bricks']):
            return "Man & van is ideal for light waste. For heavy materials like soil and rubble, a skip would be more suitable."
        
        # SYSTEMATIC COLLECTION - one field at a time
        required_fields = ['name', 'phone', 'postcode', 'volume', 'when_required', 'supplement_items']
        
        for field in required_fields:
            if not state['customer_data'].get(field):
                return self.ask_mav_field(field)
        
        # Sunday check after all data collected
        if state['customer_data'].get('when_required', '').lower() == 'sunday':
            if not state.get('sunday_lead_sent'):
                self.send_mav_lead(state)
                state['sunday_lead_sent'] = True
                state['stage'] = 'lead_sent'
                return "For Sunday collections, it's a bespoke price. Our team will call you back to arrange this."
        
        # All data collected - send lead
        if not state.get('lead_sent'):
            self.send_mav_lead(state)
            state['lead_sent'] = True
            state['stage'] = 'lead_sent'
            
            name = state['customer_data']['name']
            print(f"MAV LEAD SENT for {name}")
            return f"Perfect {name}, I have all your man & van details. Our team will call you back with pricing and to arrange your clearance."
        
        return "Our team will call you back shortly to arrange your man & van service."
    
    def ask_mav_field(self, field):
        questions = {
            'name': "What's your name?",
            'phone': "What's your phone number?",
            'postcode': "What's your postcode?",
            'volume': "How much waste do you have? Think in terms of washing machine loads - for example, 2 washing machines = 1 cubic yard.",
            'when_required': "When do you need this collected?",
            'supplement_items': "Do you have any mattresses, fridges, or upholstered furniture that need collecting?"
        }
        return questions.get(field, f"Can you tell me about {field}?")
    
    def extract_mav_data(self, message, state, msg_lower):
        # Volume
        if not state['customer_data'].get('volume'):
            volume_patterns = [
                (r'(\d+)\s*washing\s*machine', ' washing machines'),
                (r'(\d+)\s*cubic\s*yard', ' cubic yards'),
                (r'(\d+)\s*bag', ' bags'),
                ('small', '2-3 cubic yards'),
                ('large', '8-10 cubic yards')
            ]
            for pattern, suffix in volume_patterns:
                if isinstance(pattern, str):
                    if pattern in msg_lower:
                        state['customer_data']['volume'] = suffix
                        break
                else:
                    match = re.search(pattern, msg_lower)
                    if match:
                        state['customer_data']['volume'] = f"{match.group(1)}{suffix}"
                        break
        
        # When required
        if not state['customer_data'].get('when_required'):
            time_words = ['today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'asap']
            for word in time_words:
                if word in msg_lower:
                    state['customer_data']['when_required'] = word.title()
                    break
        
        # Supplement items
        if not state['customer_data'].get('supplement_items'):
            if any(item in msg_lower for item in ['mattress', 'fridge', 'sofa']):
                items = []
                if 'mattress' in msg_lower: items.append('mattresses')
                if 'fridge' in msg_lower: items.append('fridges')
                if any(word in msg_lower for word in ['sofa', 'chair']): items.append('furniture')
                state['customer_data']['supplement_items'] = ', '.join(items)
            elif any(word in msg_lower for word in ['no', 'none', 'nothing']):
                state['customer_data']['supplement_items'] = 'none'
    
    def send_mav_lead(self, state):
        customer_data = state['customer_data']
        
        subject = f"MAV LEAD - {customer_data.get('name', 'Unknown')}"
        body = f"""
MAN & VAN LEAD:

Customer: {customer_data.get('name')}
Phone: {customer_data.get('phone')}
Postcode: {customer_data.get('postcode')}
Customer Type: {state.get('customer_type')}
Volume: {customer_data.get('volume')}
When Required: {customer_data.get('when_required')}
Supplement Items: {customer_data.get('supplement_items')}

Action: Call back to discuss pricing and arrange service
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        print(f"SENDING MAV LEAD for {customer_data.get('name')}")
        send_email(subject, body)
    
    # GRAB HIRE - COMPLETE DATA COLLECTION
    def handle_grab(self, message, state, msg_lower):
        print("PROCESSING GRAB HIRE")
        
        self.extract_basic_data(message, state)
        
        # Required fields
        required_fields = ['name', 'phone', 'postcode', 'material_type', 'when_required']
        
        for field in required_fields:
            if not state['customer_data'].get(field):
                return self.ask_grab_field(field)
        
        # All data collected - send lead
        if not state.get('lead_sent'):
            self.send_grab_lead(state)
            state['lead_sent'] = True
            state['stage'] = 'lead_sent'
            
            name = state['customer_data']['name']
            print(f"GRAB LEAD SENT for {name}")
            return f"Thanks {name}, I have your grab hire details. Our team will call back with pricing and availability."
        
        return "Our specialist team will call you back about your grab hire."
    
    def ask_grab_field(self, field):
        questions = {
            'name': "What's your name?",
            'phone': "What's your phone number?",
            'postcode': "What's your postcode?",
            'material_type': "What type of material - soil/rubble (muckaway) or general waste?",
            'when_required': "When do you need this?"
        }
        return questions.get(field, f"Can you tell me about {field}?")
    
    def send_grab_lead(self, state):
        customer_data = state['customer_data']
        
        subject = f"GRAB HIRE LEAD - {customer_data.get('name', 'Unknown')}"
        body = f"""
GRAB HIRE LEAD:

Customer: {customer_data.get('name')}
Phone: {customer_data.get('phone')}
Postcode: {customer_data.get('postcode')}
Material: {customer_data.get('material_type')}
When Required: {customer_data.get('when_required')}

Action: Call back to arrange service
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        print(f"SENDING GRAB LEAD")
        send_email(subject, body)
    
    # SPECIALIST SERVICES - COMPLETE DATA COLLECTION
    def handle_specialist(self, message, state, msg_lower, service):
        print(f"PROCESSING {service.upper()}")
        
        self.extract_basic_data(message, state)
        
        required_fields = ['name', 'phone', 'postcode', 'when_required']
        
        for field in required_fields:
            if not state['customer_data'].get(field):
                return self.ask_specialist_field(field)
        
        if not state.get('lead_sent'):
            self.send_specialist_lead(state, service)
            state['lead_sent'] = True
            state['stage'] = 'lead_sent'
            
            name = state['customer_data']['name']
            print(f"{service.upper()} LEAD SENT for {name}")
            return f"Thanks {name}, our {service.replace('_', ' ')} specialist will call you back."
        
        return f"Our {service.replace('_', ' ')} team will call you back."
    
    def ask_specialist_field(self, field):
        questions = {
            'name': "What's your name?",
            'phone': "What's your phone number?",
            'postcode': "What's your postcode?",
            'when_required': "When do you need this?"
        }
        return questions.get(field, f"Can you tell me about {field}?")
    
    def send_specialist_lead(self, state, service):
        customer_data = state['customer_data']
        
        subject = f"{service.upper()} LEAD - {customer_data.get('name', 'Unknown')}"
        body = f"""
{service.upper()} LEAD:

Customer: {customer_data.get('name')}
Phone: {customer_data.get('phone')}
Postcode: {customer_data.get('postcode')}
When Required: {customer_data.get('when_required')}

Service: {service.replace('_', ' ').title()}
Action: Specialist callback within 2 hours
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        print(f"SENDING {service.upper()} LEAD")
        send_email(subject, body)
    
    # SKIP COLLECTION
    def handle_skip_collection(self, message, state, msg_lower):
        print("PROCESSING SKIP COLLECTION")
        
        self.extract_basic_data(message, state)
        
        required_fields = ['name', 'phone', 'postcode', 'address']
        
        for field in required_fields:
            if not state['customer_data'].get(field):
                if field == 'address':
                    return "What's your full address?"
                else:
                    return self.ask_specialist_field(field)
        
        if not state.get('lead_sent'):
            self.send_collection_lead(state)
            state['lead_sent'] = True
            state['stage'] = 'lead_sent'
            
            print("SKIP COLLECTION LEAD SENT")
            return "Thanks, we can arrange skip collection. Our team will call you back to confirm."
        
        return "Our team will arrange your skip collection."
    
    def send_collection_lead(self, state):
        customer_data = state['customer_data']
        
        subject = f"SKIP COLLECTION - {customer_data.get('name', 'Unknown')}"
        body = f"""
SKIP COLLECTION REQUEST:

Customer: {customer_data.get('name')}
Phone: {customer_data.get('phone')}
Address: {customer_data.get('address')}
Postcode: {customer_data.get('postcode')}

Action: Arrange collection within 1-4 days
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        print("SENDING SKIP COLLECTION REQUEST")
        send_email(subject, body)
    
    # GENERAL CONVERSATION
    def handle_general(self, message, state, msg_lower):
        if any(word in msg_lower for word in ['price', 'cost', 'quote']):
            return "I can help with pricing. What service do you need - skip hire, man & van clearance, or something else?"
        elif 'permit' in msg_lower:
            return "We arrange permits for you and include the cost in your quote. What size skip do you need?"
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "system",
                    "content": "You are Jennifer from Waste King. Be helpful and direct. Ask what service they need if unclear. Keep responses under 2 sentences."
                }, {
                    "role": "user",
                    "content": message
                }],
                max_tokens=50,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except:
            return "I can help with skip hire, man & van clearance, grab hire, and specialist services. What do you need?"
    
    # DATA EXTRACTION
    def extract_basic_data(self, message, state):
        # Name
        if not state['customer_data'].get('name'):
            name_patterns = [
                r'name\s+is\s+([A-Z][a-z]+)',
                r'i\'?m\s+([A-Z][a-z]+)',
                r'call\s+me\s+([A-Z][a-z]+)',
                r'^([A-Z][a-z]+)$'
            ]
            for pattern in name_patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    name = match.group(1)
                    if name.lower() not in ['yes', 'no', 'hello', 'hi']:
                        state['customer_data']['name'] = name
                        print(f"EXTRACTED NAME: {name}")
                        break
        
        # Phone
        if not state['customer_data'].get('phone'):
            phone_patterns = [
                r'\b(07\d{9})\b',
                r'\b(\d{11})\b'
            ]
            for pattern in phone_patterns:
                match = re.search(pattern, message)
                if match:
                    state['customer_data']['phone'] = match.group(1)
                    print(f"EXTRACTED PHONE: {match.group(1)}")
                    break
        
        # Postcode
        if not state['customer_data'].get('postcode'):
            postcode_pattern = r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b'
            match = re.search(postcode_pattern, message.upper())
            if match:
                postcode = match.group(1).replace(' ', '')
                state['customer_data']['postcode'] = postcode
                print(f"EXTRACTED POSTCODE: {postcode}")
        
        # Skip size
        if not state['customer_data'].get('skip_size'):
            for size in ['4yd', '6yd', '8yd', '12yd']:
                size_num = size.replace('yd', '')
                if any(variant in message.lower() for variant in [f'{size_num} yard', f'{size_num}yd', f'{size_num}-yard']):
                    state['customer_data']['skip_size'] = size
                    print(f"EXTRACTED SKIP SIZE: {size}")
                    break
        
        # Address for skip collection
        if not state['customer_data'].get('address') and any(word in message.lower() for word in ['street', 'road', 'avenue', 'close', 'way']):
            state['customer_data']['address'] = message.strip()
            print(f"EXTRACTED ADDRESS: {message.strip()}")

# Flask App
app = Flask(__name__)
CORS(app)

agent = WasteKingAgent()
conversation_counter = 0

def get_conversation_id():
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:06d}"

@app.route('/api/wasteking', methods=['POST'])
def process_message():
    try:
        data = request.get_json()
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('conversation_id') or data.get('elevenlabs_conversation_id') or get_conversation_id()
        
        if not customer_message:
            return jsonify({"success": False, "message": "No message provided"}), 400
        
        response_text, stage = agent.process_message(customer_message, conversation_id)
        
        return jsonify({
            "success": True,
            "message": response_text,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
            "stage": stage
        })
        
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "message": "I'll connect you with our team who can help immediately.",
            "error": str(e)
        }), 500

@app.route('/')
def index():
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>WasteKing Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat-box { background: white; border: 1px solid #ddd; padding: 15px; border-radius: 8px; text-align: center; }
        .conversations { background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; }
        .conv-item { background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>WasteKing System Dashboard</h1>
        <p>Live conversation monitoring</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <h3 id="total-conversations">0</h3>
            <p>Total Conversations</p>
        </div>
        <div class="stat-box">
            <h3 id="active-conversations">0</h3>
            <p>Active Now</p>
        </div>
        <div class="stat-box">
            <h3 id="bookings-completed">0</h3>
            <p>Bookings Completed</p>
        </div>
    </div>
    
    <div class="conversations">
        <h2>Recent Conversations</h2>
        <div id="conversation-list">Loading...</div>
    </div>

    <script>
        function loadDashboard() {
            fetch('/api/dashboard')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('total-conversations').textContent = data.total || 0;
                        document.getElementById('active-conversations').textContent = data.active || 0;
                        document.getElementById('bookings-completed').textContent = data.completed || 0;
                        
                        const convHTML = (data.conversations || []).map(conv => `
                            <div class="conv-item">
                                <strong>${conv.id}</strong> - ${conv.stage}
                                ${conv.service ? `(${conv.service})` : ''}
                                <br><small>${new Date().toLocaleString()}</small>
                                ${conv.customer ? `<br><small>Customer: ${conv.customer}</small>` : ''}
                            </div>
                        `).join('');
                        
                        document.getElementById('conversation-list').innerHTML = convHTML || '<p>No conversations yet</p>';
                    }
                });
        }
        
        loadDashboard();
        setInterval(loadDashboard, 5000);
    </script>
</body>
</html>
""")

@app.route('/api/dashboard')
def dashboard_api():
    try:
        conversations = agent.conversations
        
        total = len(conversations)
        active = sum(1 for conv in conversations.values() if conv.get('stage') not in ['completed', 'lead_sent'])
        completed = sum(1 for conv in conversations.values() if conv.get('stage') == 'completed')
        
        recent_convs = []
        for conv_id, conv_data in list(conversations.items())[-10:]:
            recent_convs.append({
                'id': conv_id,
                'stage': conv_data.get('stage', 'unknown'),
                'service': conv_data.get('service_type', ''),
                'customer': conv_data.get('customer_data', {}).get('name', '')
            })
        
        return jsonify({
            "success": True,
            "total": total,
            "active": active,
            "completed": completed,
            "conversations": recent_convs
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    print("WasteKing Agent Starting...")
    print("Skip hire: Auto-booking with SMS confirmations")
    print("All services: Complete lead generation before transfer")
    print("Clean console logging enabled")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
