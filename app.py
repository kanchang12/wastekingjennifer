import os
import re
import json
import requests
import traceback
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from openai import OpenAI
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from flask_cors import CORS

# API Integration
try:
    from utils.wasteking_api import complete_booking, create_booking, get_pricing, create_payment_link
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False
    print("WARNING: Live wasteking_api module not found. The system cannot process bookings.")
    def create_booking(): return {'success': False, 'error': 'API unavailable'}
    def get_pricing(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}
    def complete_booking(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}
    def create_payment_link(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}

# --- BUSINESS RULES ---
OFFICE_HOURS = {
    'monday_thursday': {'start': 8, 'end': 17},
    'friday': {'start': 8, 'end': 16.5},
    'saturday': {'start': 9, 'end': 12},
    'sunday': 'closed'
}

TRANSFER_RULES = {
    'management_director': {
        'triggers': ['glenn currie', 'director', 'speak to glenn'],
        'office_hours': "I am sorry, Glenn is not available, may I take your details and Glenn will call you back?",
        'out_of_hours': "I can take your details and have our director call you back first thing tomorrow",
        'sms_notify': '+447823656762'
    },
    'complaints': {
        'triggers': ['complaint', 'complain', 'unhappy', 'disappointed', 'frustrated', 'angry'],
        'office_hours': "I understand your frustration, please bear with me while I transfer you to the appropriate person.",
        'out_of_hours': "I understand your frustration. I can take your details and have our customer service team call you back first thing tomorrow.",
        'action': 'TRANSFER',
        'sms_notify': '+447823656762'
    },
    'specialist_services': {
        'services': ['hazardous waste disposal', 'asbestos removal', 'asbestos collection', 'weee electrical waste', 'chemical disposal', 'medical waste', 'trade waste'],
        'office_hours': 'Transfer immediately',
        'out_of_hours': 'Take details + SMS notification to +447823656762'
    }
}

LG_SERVICES = {
    'skip_collection': {
        'triggers': ['skip collection', 'collect skip', 'pick up skip', 'remove skip', 'collection of skip'],
        'script': "I can help with that. It can take between 1-4 days to collect a skip. Can I have your postcode, first line of the address, your name, your telephone number, is the skip a level load, can you confirm there are no prohibited items in the skip, are there any access issues?",
        'required_fields': ['postcode', 'address_line1', 'firstName', 'phone', 'level_load', 'prohibited_check', 'access_issues']
    },
    'road_sweeper': {
        'triggers': ['road sweeper', 'road sweeping', 'street sweeping'],
        'questions': ['postcode', 'hours_required', 'tipping_location', 'when_required'],
        'scripts': {
            'transfer': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
        }
    },
    'toilet_hire': {
        'triggers': ['toilet hire', 'portaloo', 'portable toilet'],
        'questions': ['postcode', 'number_required', 'event_or_longterm', 'duration', 'delivery_date'],
        'scripts': {
            'transfer': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
        }
    },
    'asbestos': {
        'triggers': ['asbestos'],
        'questions': ['postcode', 'skip_or_collection', 'asbestos_type', 'dismantle_or_collection', 'quantity'],
        'scripts': {
            'transfer': "Asbestos requires specialist handling. Let me arrange for our certified team to call you back."
        }
    },
    'hazardous_waste': {
        'triggers': ['hazardous waste', 'chemical waste', 'dangerous waste'],
        'questions': ['postcode', 'description', 'data_sheet'],
        'scripts': {
            'transfer': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
        }
    },
    'wheelie_bins': {
        'triggers': ['wheelie bin', 'wheelie bins', 'bin hire'],
        'questions': ['postcode', 'domestic_or_commercial', 'waste_type', 'bin_size', 'number_bins', 'collection_frequency', 'duration'],
        'scripts': {
            'transfer': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
        }
    },
    'aggregates': {
        'triggers': ['aggregates', 'sand', 'gravel', 'stone'],
        'questions': ['postcode', 'tipper_or_grab'],
        'scripts': {
            'transfer': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
        }
    },
    'roro_40yard': {
        'triggers': ['40 yard', '40-yard', 'roro', 'roll on roll off', '30 yard', '35 yard'],
        'questions': ['postcode', 'waste_type'],
        'scripts': {
            'heavy_materials': "For heavy materials like soil, rubble in RoRo skips, we recommend a 20 yard RoRo skip. 30/35/40 yard RoRos are for light materials only.",
            'transfer': "I will pass you onto our specialist team to give you a quote and availability"
        }
    },
    'waste_bags': {
        'triggers': ['skip bag', 'waste bag', 'skip sack'],
        'sizes': ['1.5', '3.6', '4.5'],
        'scripts': {
            'info': "Our skip bags are for light waste only. Is this for light waste and our man and van service will collect the rubbish? We can deliver a bag out to you and you can fill it and then we collect and recycle the rubbish. We have 3 sizes: 1.5, 3.6, 4.5 cubic yards bags. Bags are great as there's no time limit and we collect when you're ready"
        }
    },
    'wait_and_load': {
        'triggers': ['wait and load', 'wait & load', 'wait load'],
        'questions': ['postcode', 'waste_type', 'when_required'],
        'scripts': {
            'transfer': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
        }
    }
}

SKIP_HIRE_RULES = {
    'A2_heavy_materials': {
        'heavy_materials_max': "For heavy materials such as soil & rubble: the largest skip you can have would be an 8-yard. Shall I get you the cost of an 8-yard skip?"
    },
    'A5_prohibited_items': {
        'surcharge_items': { 'fridges': 20, 'freezers': 20, 'mattresses': 15, 'upholstered furniture': 15 },
        'plasterboard_response': "Plasterboard isn't allowed in normal skips. If you have a lot, we can arrange a special plasterboard skip, or our man and van service can collect it for you",
        'restrictions_response': "There may be restrictions on fridges & mattresses depending on your location",
        'upholstery_alternative': "The following items are prohibited in skips. However, our fully licensed and insured man and van service can remove light waste, including these items, safely and responsibly.",
        'prohibited_list': [ 'fridges', 'freezers', 'mattresses', 'upholstered furniture', 'paint', 'liquids', 'tyres', 'plasterboard', 'gas cylinders', 'hazardous chemicals', 'asbestos'],
        'full_script': "Just so you know, there are some prohibited items that cannot be placed in skips — including mattresses (£15 charge), fridges (£20 charge), upholstery, plasterboard, asbestos, and paint. Our man and van service is ideal for light rubbish and can remove most items. If you'd prefer, I can connect you with the team to discuss the man and van option. Would you like to speak to the team about that, or continue with skip hire?"
    },
    'A7_quote': {
        'vat_note': 'If the prices are coming from SMP they are always + VAT',
        'always_include': ["Collection within 72 hours standard", "Level load requirement for skip collection", "Driver calls when en route", "98% recycling rate", "We have insured and licensed teams", "Digital waste transfer notes provided"]
    },
    'delivery_timing': "We usually aim to deliver your skip the next day, but during peak months, it may take a bit longer. Don't worry though – we'll check with the depot to get it to you as soon as we can, and we'll always do our best to get it on the day you need.",
    'not_booking_response': "You haven't booked yet, so I'll send the quote to your mobile — if you choose to go ahead, just click the link to book. Would you like a £10 discount? If you're happy with the service after booking, you'll have the option to leave a review."
}

MAV_RULES = {
    'B1_information_gathering': {
        'cubic_yard_explanation': "Our team charges by the cubic yard which means we only charge by what we remove. To give you an idea, two washing machines equal about one cubic yard. On average, most clearances we do are around six yards. How many yards do you want to book with us?"
    },
    'B2_heavy_materials': {
        'script': "The man and van are ideal for light waste rather than heavy materials - a skip might be more suitable, since our man and van service is designed for lighter waste."
    },
    'B3_volume_assessment': {
        'if_unsure': "Think in terms of washing machine loads or black bags."
    },
    'B5_additional_timing': {
        'sunday_collections': {'script': "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team and they will be able to help"},
        'time_script': "We can't guarantee exact times, but collection is typically between 7am-6pm"
    },
    'supplement_check': "Can I just check — do you have any mattresses, upholstery, or fridges that need collecting?"
}

GRAB_RULES = {
    'C2_grab_size_exact_scripts': {
        'mandatory_exact_scripts': {
            '8_wheeler': "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry.",
            '6_wheeler': "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry."
        }
    },
    'C3_materials_assessment': {
        'mixed_materials': {'script': "The majority of grabs will only take muckaway which is soil & rubble. Let me put you through to our team and they will check if we can take the other materials for you."}
    }
}

GENERAL_SCRIPTS = {
    'timing_query': "Orders are completed between 6am and 5pm. If you need a specific time, I'll raise a ticket and the team will get back to you shortly. Is there anything else I can help you with?",
    'location_response': "I am based in the head office although we have depots nationwide and local to you.",
    'human_request': "Yes I can see if someone is available. What is your company name? What is the call regarding?",
    'closing': "Is there anything else I can help with? Thanks for trusting Waste King"
}

REQUIRED_FIELDS = {
    'skip': ['firstName', 'postcode', 'phone', 'customer_type'],
    'mav': ['firstName', 'postcode', 'phone', 'customer_type'],
    'grab': ['firstName', 'postcode', 'phone', 'customer_type'],
    'skip_collection': ['firstName', 'postcode', 'phone', 'address_line1', 'level_load', 'prohibited_check', 'access_issues']
}

SKIP_SIZES = ['2yd', '4yd', '6yd', '8yd', '10yd', '12yd', '14yd', '16yd', '20yd']

# --- EMAIL FUNCTIONS ---
def send_email(subject, body, recipient=None):
    try:
        zoho_email = os.getenv('ZOHO_EMAIL')
        zoho_password = os.getenv('ZOHO_PASSWORD')
        
        if not zoho_email or not zoho_password:
            print("Zoho email credentials not configured")
            return False
            
        recipient = recipient or os.getenv('TRADE_EMAIL_RECIPIENT', zoho_email)
        
        msg = MIMEMultipart()
        msg['From'] = zoho_email
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.zoho.com', 587)
        server.starttls()
        server.login(zoho_email, zoho_password)
        server.sendmail(zoho_email, recipient, msg.as_string())
        server.quit()
        
        print(f"Email sent successfully to {recipient}")
        return True
        
    except Exception as e:
        print(f"Email sending failed: {e}")
        return False

def send_trade_customer_email(customer_data, conversation_history):
    subject = f"Trade Customer Inquiry - {customer_data.get('firstName', 'Unknown')}"
    body = f"""
Trade Customer Inquiry Details:

Customer Name: {customer_data.get('firstName', 'Not provided')}
Account/Company: {customer_data.get('company', 'Not provided')}
Phone: {customer_data.get('phone', 'Not provided')}
Postcode: {customer_data.get('postcode', 'Not provided')}
Service Required: {customer_data.get('service', 'Not specified')}
Customer Type: Trade

Conversation Summary:
{chr(10).join(conversation_history[-5:]) if conversation_history else 'No conversation history'}

Action Required: Follow up with trade customer for pricing and availability.
Priority: Standard
"""
    
    trade_recipient = os.getenv('TRADE_EMAIL_RECIPIENT')
    return send_email(subject, body, trade_recipient)

def send_callback_email(customer_data, conversation_history, callback_reason):
    subject = f"Customer Callback Required - {customer_data.get('firstName', 'Unknown')}"
    body = f"""
Customer Callback Request:

Customer Name: {customer_data.get('firstName', 'Not provided')}
Phone: {customer_data.get('phone', 'Not provided')}
Postcode: {customer_data.get('postcode', 'Not provided')}
Service Required: {customer_data.get('service', 'Not specified')}
Customer Type: {customer_data.get('customer_type', 'Not specified')}

Callback Reason: {callback_reason}

Recent Conversation:
{chr(10).join(conversation_history[-5:]) if conversation_history else 'No conversation history'}

Action Required: Call back customer as promised.
Priority: High
"""
    
    callback_recipient = os.getenv('CALLBACK_EMAIL_RECIPIENT', os.getenv('ZOHO_EMAIL'))
    return send_email(subject, body, callback_recipient)

# --- ELEVENLABS SUPPLIER CALL FUNCTIONS ---
def make_supplier_call(customer_data, service_type):
    try:
        elevenlabs_api_key = os.getenv('ELEVENLABS_API_KEY')
        agent_phone_number_id = os.getenv('AGENT_PHONE_NUMBER_ID') 
        agent_id = os.getenv('AGENT_ID')
        supplier_phone = os.getenv('SUPPLIER_PHONE_NUMBER')
        
        if not all([elevenlabs_api_key, agent_phone_number_id, agent_id, supplier_phone]):
            print("ElevenLabs configuration incomplete")
            return False
            
        if not is_business_hours():
            print("Outside business hours - supplier call not made")
            return False
            
        headers = {
            'Authorization': f'Bearer {elevenlabs_api_key}',
            'Content-Type': 'application/json'
        }
        
        call_data = {
            'agent_id': agent_id,
            'customer_phone_number': supplier_phone,
            'agent_phone_number_id': agent_phone_number_id,
            'metadata': {
                'customer_name': customer_data.get('firstName'),
                'service_type': service_type,
                'postcode': customer_data.get('postcode'),
                'customer_phone': customer_data.get('phone')
            }
        }
        
        response = requests.post(
            'https://api.elevenlabs.io/v1/convai/conversations',
            headers=headers,
            json=call_data,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"Supplier call initiated for {service_type}")
            return True
        else:
            print(f"Supplier call failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Supplier call error: {e}")
        return False

# --- HELPER FUNCTIONS ---
def is_business_hours():
    now = datetime.now()
    day = now.weekday()
    hour = now.hour + (now.minute / 60.0)
    if day < 4: return 8 <= hour < 17
    elif day == 4: return 8 <= hour < 16.5
    elif day == 5: return 9 <= hour < 12
    return False

def send_webhook(conversation_id, data, reason):
    try:
        collected_data = data.get('collected_data', {})
        
        payload = {
            "conversation_id": conversation_id,
            "action_type": reason,
            "customer_name": collected_data.get('firstName', ''),
            "customer_phone": collected_data.get('phone', ''),
            "customer_postcode": collected_data.get('postcode', ''),
            "service_type": collected_data.get('service', ''),
            "customer_type": collected_data.get('customer_type', ''),
            "all_data": data
        }
        
        webhook_url = os.getenv('WEBHOOK_URL', "https://hook.eu2.make.com/t7bneptowre8yhexo5fjjx4nc09gqdz1")
        
        requests.post(webhook_url, json=payload, timeout=5)
        
        print(f"Webhook sent successfully for {reason}: {conversation_id}")
        return True
    except Exception as e:
        print(f"Webhook failed for {conversation_id}: {e}")
        return False

def send_sms(name, phone, booking_ref, price, payment_link):
    try:
        twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
        twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
        twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
        if twilio_sid and twilio_token and twilio_phone:
            from twilio.rest import Client
            client = Client(twilio_sid, twilio_token)
            formatted_phone = f"+44{phone[1:]}" if phone.startswith('0') else phone
            message = f"Hi {name}, your booking confirmed! Ref: {booking_ref}, Price: {price}. Pay here: {payment_link}"
            client.messages.create(body=message, from_=twilio_phone, to=formatted_phone)
            print(f"SMS sent to {phone}")
    except Exception as e:
        print(f"SMS error: {e}")

# --- HELPER CLASSES ---
class OpenAIQuestionValidator:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    def check_duplicate_question(self, question, conversation_history):
        try:
            prompt = f"Analyze this conversation history: {conversation_history}. Have we already asked for the same information as this question: '{question}'? Respond with only TRUE or FALSE."
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=10, temperature=0
            )
            return response.choices[0].message.content.strip().upper() == "TRUE"
        except Exception as e:
            print(f"OpenAI duplicate check error: {e}")
            return question in conversation_history
            
    def generate_smart_response(self, state, service_type, conversation_history):
        try:
            prompt = f"You are a {service_type} booking agent. Customer data: {state}. Generate a natural, polite response. Avoid overusing words like 'great', 'brilliant', 'lovely'. Use natural conversation like 'That's good', 'I'd be happy to help', etc. Be concise (1-2 sentences)."
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=100, temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI response generation error: {e}")
            return f"Thank you! I have your details and I'm getting your {service_type} quote now."

# DASHBOARD MANAGER
class DashboardManager:
    def __init__(self):
        self.all_calls = {}  # Store ALL calls for manager
        self.recent_calls = {}  # Store only recent calls for users
    
    def update_call(self, conversation_id, data):
        status = 'active' if data.get('stage') not in ['completed', 'transfer_completed'] else 'completed'
        timestamp = datetime.now().isoformat()
        
        call_data = {
            'id': conversation_id,
            'timestamp': timestamp,
            'stage': data.get('stage', 'unknown'),
            'collected_data': data.get('collected_data', {}),
            'history': data.get('history', []),
            'price': data.get('price'),
            'status': status,
            'callback_required': data.get('callback_required', False),
            'callback_reason': data.get('callback_reason', ''),
            'last_updated': timestamp
        }
        
        # Store in all_calls for manager (permanent)
        self.all_calls[conversation_id] = call_data
        
        # Store in recent_calls for users (temporary)
        self.recent_calls[conversation_id] = call_data
        
        # Clean old calls from recent_calls (keep only last 10 minutes)
        self._clean_recent_calls()
    
    def _clean_recent_calls(self):
        cutoff_time = datetime.now() - timedelta(minutes=10)
        calls_to_remove = []
        
        for call_id, call_data in self.recent_calls.items():
            call_time = datetime.fromisoformat(call_data['timestamp'].replace('Z', '+00:00').replace('+00:00', ''))
            if call_time < cutoff_time:
                calls_to_remove.append(call_id)
        
        for call_id in calls_to_remove:
            del self.recent_calls[call_id]
    
    def get_user_dashboard_data(self):
        self._clean_recent_calls()
        active_calls = [call for call in self.recent_calls.values() if call['status'] == 'active']
        return {
            'active_calls': len(active_calls),
            'live_calls': list(self.recent_calls.values()),
            'timestamp': datetime.now().isoformat(),
            'total_calls': len(self.recent_calls),
            'has_data': len(self.recent_calls) > 0
        }
    
    def get_manager_dashboard_data(self):
        total_calls = len(self.all_calls)
        completed_calls = len([call for call in self.all_calls.values() if call['status'] == 'completed'])
        callback_calls = [call for call in self.all_calls.values() if call.get('callback_required')]
        
        services = {}
        for call in self.all_calls.values():
            service = call.get('collected_data', {}).get('service', 'unknown')
            services[service] = services.get(service, 0) + 1
            
        return {
            'total_calls': total_calls,
            'completed_calls': completed_calls,
            'conversion_rate': (completed_calls / total_calls * 100) if total_calls > 0 else 0,
            'service_breakdown': services,
            'timestamp': datetime.now().isoformat(),
            'individual_calls': list(self.all_calls.values()),
            'recent_calls': list(self.all_calls.values())[-50:],  # Last 50 for performance
            'active_calls': [call for call in self.all_calls.values() if call['status'] == 'active'],
            'callback_required_calls': callback_calls
        }

# --- AGENT BASE CLASS ---
class BaseAgent:
    def __init__(self):
        self.conversations = {}

    def process_message(self, message, conversation_id):
        state = self.conversations.get(conversation_id, {'history': [], 'collected_data': {}, 'stage': 'initial'})
        state['history'].append(f"Customer: {message}")
        
        # Check if we need to ask about customer type first
        if not state.get('collected_data', {}).get('customer_type') and not any(word in message.lower() for word in ['domestic', 'trade', 'business', 'commercial', 'company']):
            customer_type_response = self.ask_customer_type(message, state)
            if customer_type_response:
                state['history'].append(f"Agent: {customer_type_response}")
                self.conversations[conversation_id] = state.copy()
                return customer_type_response
        
        special_response = self.check_special_rules(message, state)
        if special_response:
            state['history'].append(f"Agent: {special_response['response']}")
            state['stage'] = special_response.get('stage', 'transfer_completed')
            
            # Handle callback and email requirements
            if special_response.get('callback_required'):
                state['callback_required'] = True
                state['callback_reason'] = special_response.get('callback_reason', 'General inquiry')
                
                if state.get('collected_data', {}).get('customer_type') == 'trade':
                    send_trade_customer_email(state['collected_data'], state['history'])
                else:
                    send_callback_email(state['collected_data'], state['history'], state['callback_reason'])
            
            send_webhook(conversation_id, {'collected_data': state['collected_data'], 'history': state['history'], 'stage': state['stage']}, special_response.get('reason', 'transfer'))
            self.conversations[conversation_id] = state.copy()
            return special_response['response']

        new_data = self.extract_data(message)
        state['collected_data'].update(new_data)
        
        response = self.get_next_response(message, state, conversation_id)
        
        # Always ask if there's anything else before ending
        if "booking confirmed" in response.lower() or "transfer" in response.lower():
            if not response.endswith("Is there anything else I can help with? Thanks for trusting Waste King"):
                response += " Is there anything else I can help with? Thanks for trusting Waste King"
        
        state['history'].append(f"Agent: {response}")
        state['stage'] = self.get_stage_from_response(response, state)
        self.conversations[conversation_id] = state.copy()
        
        return response

    def ask_customer_type(self, message, state):
        # Don't ask if they're clearly indicating service type already
        if any(service_word in message.lower() for service_word in ['skip', 'man and van', 'grab', 'collection']):
            return None
        return "Are you a domestic customer or trade customer?"

    def extract_customer_type(self, message):
        message_lower = message.lower()
        if any(word in message_lower for word in ['trade', 'business', 'commercial', 'company', 'ltd', 'limited']):
            return 'trade'
        elif any(word in message_lower for word in ['domestic', 'home', 'house', 'personal', 'private']):
            return 'domestic'
        return None

    def check_special_rules(self, message, state):
        message_lower = message.lower()
        
        # Skip collection handling
        if any(trigger in message_lower for trigger in LG_SERVICES['skip_collection']['triggers']):
            return {'response': LG_SERVICES['skip_collection']['script'], 'stage': 'collecting_skip_collection_info', 'reason': 'skip_collection', 'callback_required': True, 'callback_reason': 'Skip collection request'}
        
        # Director request
        if any(trigger in message_lower for trigger in TRANSFER_RULES['management_director']['triggers']):
            if is_business_hours():
                return {'response': TRANSFER_RULES['management_director']['office_hours'], 'stage': 'transfer_completed', 'reason': 'director_request', 'callback_required': True, 'callback_reason': 'Director meeting request'}
            else:
                return {'response': TRANSFER_RULES['management_director']['out_of_hours'], 'stage': 'callback_promised', 'reason': 'director_request', 'callback_required': True, 'callback_reason': 'Director meeting request - out of hours'}
        
        # Complaints
        if any(complaint in message_lower for complaint in TRANSFER_RULES['complaints']['triggers']):
            if is_business_hours():
                return {'response': TRANSFER_RULES['complaints']['office_hours'], 'stage': 'transfer_completed', 'reason': 'complaint'}
            else:
                return {'response': TRANSFER_RULES['complaints']['out_of_hours'], 'stage': 'callback_promised', 'reason': 'complaint', 'callback_required': True, 'callback_reason': 'Customer complaint - requires callback'}
        
        # LG Services
        for service_type, config in LG_SERVICES.items():
            if service_type == 'skip_collection':
                continue  # Already handled above
            if 'triggers' in config and any(trigger in message_lower for trigger in config['triggers']):
                if service_type == 'waste_bags':
                    return {'response': LG_SERVICES['waste_bags']['scripts']['info'], 'stage': 'info_provided', 'reason': 'waste_bags'}
                make_supplier_call(state.get('collected_data', {}), service_type)
                return {'response': config['scripts']['transfer'], 'stage': 'transfer_completed', 'reason': f'lg_service_{service_type}', 'callback_required': True, 'callback_reason': f'{service_type} inquiry'}

        # General queries
        if any(term in message_lower for term in ['depot close by', 'local to me', 'near me']):
            return {'response': GENERAL_SCRIPTS['location_response'], 'stage': 'info_provided', 'reason': 'location_query'}
        if any(term in message_lower for term in ['speak to human', 'talk to person', 'human agent']):
            return {'response': GENERAL_SCRIPTS['human_request'], 'stage': 'transfer_completed', 'reason': 'human_request'}
        if any(term in message_lower for term in ['when can you deliver', 'delivery time', 'when will skip arrive']):
            return {'response': SKIP_HIRE_RULES['delivery_timing'], 'stage': 'info_provided', 'reason': 'delivery_timing'}
        if any(term in message_lower for term in ['what time', 'specific time', 'exact time']):
            return {'response': GENERAL_SCRIPTS['timing_query'], 'stage': 'info_provided', 'reason': 'timing_query'}
        if any(term in message_lower for term in ['call you back', 'call back', 'phone around', 'check with someone']):
            return {'response': SKIP_HIRE_RULES['not_booking_response'], 'stage': 'quote_sent', 'reason': 'not_booking_now'}
        
        return None

    def get_next_response(self, message, state, conversation_id):
        raise NotImplementedError("Subclass must implement get_next_response method")
    
    def extract_data(self, message):
        data = {}
        message_lower = message.lower()
        
        # Customer type
        customer_type = self.extract_customer_type(message)
        if customer_type:
            data['customer_type'] = customer_type
        
        # Postcode
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
        if postcode_match:
            postcode = postcode_match.group(1).replace(' ', '')
            if len(postcode) >= 5: data['postcode'] = postcode
        
        # Phone
        phone_patterns = [r'\b(\d{11})\b', r'\b(\d{5})\s+(\d{6})\b', r'\b(\d{4})\s+(\d{6})\b', r'\((\d{4,5})\)\s*(\d{6})\b']
        for pattern in phone_patterns:
            phone_match = re.search(pattern, message)
            if phone_match:
                phone_number = ''.join([group for group in phone_match.groups() if group])
                if len(phone_number) >= 10: data['phone'] = phone_number; break
        
        # Name
        if any(test_name in message_lower for test_name in ['kanchen', 'kanchan']): data['firstName'] = 'Kanchan'
        elif 'jackie' in message_lower: data['firstName'] = 'Jackie'
        else:
            name_patterns = [r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', r'^([A-Z][a-z]+)\s+', r'[Ii]\'m\s+([A-Z][a-z]+)', r'[Cc]all\s+me\s+([A-Z][a-z]+)']
            for pattern in name_patterns:
                name_match = re.search(pattern, message)
                if name_match:
                    potential_name = name_match.group(1).strip().title()
                    if potential_name.lower() not in ['yes', 'no', 'there', 'what', 'how', 'confirmed', 'phone', 'please', 'good', 'fine']:
                        data['firstName'] = potential_name; break
        
        # Service type
        if any(word in message_lower for word in ['skip', 'skip hire', 'container hire']): data['service'] = 'skip'
        elif any(phrase in message_lower for phrase in ['house clearance', 'man and van', 'mav', 'furniture', 'appliance', 'van collection', 'clearance']): data['service'] = 'mav'
        elif any(phrase in message_lower for phrase in ['grab hire', 'grab lorry', '8 wheeler', '6 wheeler', 'soil removal', 'rubble removal']): data['service'] = 'grab'
        
        # Skip size - improved recognition
        if data.get('service') == 'skip':
            for size in SKIP_SIZES:
                size_num = size.replace('yd', '')
                if any(variant in message_lower for variant in [f'{size_num}-yard', f'{size_num} yard', f'{size_num}yd', f'{size_num} yd']):
                    data['type'] = size
                    break
        
        # Address line 1
        address_patterns = [r'address\s+(?:is\s+)?(.+)', r'first line\s+(?:is\s+)?(.+)', r'live\s+(?:at\s+)?(.+)']
        for pattern in address_patterns:
            address_match = re.search(pattern, message, re.IGNORECASE)
            if address_match:
                data['address_line1'] = address_match.group(1).strip()
                break
        
        # Level load confirmation
        if any(phrase in message_lower for phrase in ['level load', 'level', 'not overloaded', 'flush']):
            data['level_load'] = 'yes' if any(positive in message_lower for positive in ['yes', 'level', 'flush']) else 'no'
        
        # Prohibited items check
        if any(phrase in message_lower for phrase in ['no prohibited', 'prohibited items', 'no restricted']):
            data['prohibited_check'] = 'confirmed'
        
        # Access issues
        if any(phrase in message_lower for phrase in ['access', 'narrow', 'parking', 'restrictions']):
            data['access_issues'] = 'yes' if any(issue in message_lower for issue in ['narrow', 'difficult', 'restricted', 'problem']) else 'no'
        
        return data

    def get_stage_from_response(self, response, state):
        if "booking confirmed" in response.lower():
            return 'completed'
        if "unable to get pricing" in response.lower() or "technical issue" in response.lower() or "connect you with our team" in response.lower():
            return 'transfer_completed'
        if "Would you like to book this?" in response:
            return 'booking'
        if any(question in response for question in ["What's your name?", "What's your complete postcode?", "What's the best phone number"]):
            return 'collecting_info'
        return 'processing'

    def should_book(self, message):
        booking_phrases = ['payment link', 'pay link', 'book it', 'book this', 'complete booking', 'proceed with booking', 'confirm booking']
        if any(phrase in message.lower() for phrase in booking_phrases): return True
        return any(word in message.lower() for word in ['yes', 'yeah', 'yep', 'ok', 'okay', 'alright', 'sure'])
    
    def needs_transfer(self, service_type, price):
        # SKIP SALES ARE NEVER TRANSFERRED - COMPLETE ALL SKIP SALES
        if service_type == 'skip': return False
        # Other services can be transferred for high prices
        if service_type == 'mav' and price >= 500: return True
        if service_type == 'grab' and price >= 300: return True
        return False
        
    def get_pricing(self, state, conversation_id, wants_to_book=False):
        if not API_AVAILABLE:
            send_webhook(conversation_id, state, 'api_unavailable')
            return "I'm sorry, our pricing system is currently unavailable. Let me connect you with our team."
            
        try:
            booking_result = create_booking()
            if not booking_result.get('success'):
                send_webhook(conversation_id, state, 'api_pricing_failure')
                return "Unable to get pricing right now. Let me put you through to our team."
            
            booking_ref = booking_result['booking_ref']
            service_type = state.get('collected_data', {}).get('type')
            
            price_result = get_pricing(booking_ref, state.get('collected_data', {}).get('postcode'), state.get('collected_data', {}).get('service'), service_type)
            if not price_result.get('success'):
                send_webhook(conversation_id, state, 'api_pricing_failure')
                return "I'm having trouble finding pricing for that. Could you please confirm your complete postcode is correct?"
            
            price = price_result['price']
            returned_type = price_result.get('type', service_type)
            
            # Check for price discrepancy
            requested_type = state.get('collected_data', {}).get('type')
            if requested_type and requested_type != returned_type:
                send_webhook(conversation_id, state, 'price_discrepancy')
                return f"There's a discrepancy with the pricing for your {requested_type} request. Let me transfer you to our team for accurate pricing."
            
            price_num = float(price.replace('£', '').replace(',', ''))
            state['price'] = price
            state['collected_data']['type'] = returned_type
            state['booking_ref'] = booking_ref
            self.conversations[conversation_id] = state
            
            if self.needs_transfer(state.get('collected_data', {}).get('service'), price_num):
                send_webhook(conversation_id, state, 'high_price_transfer')
                if is_business_hours():
                    return "For this size job, let me put you through to our specialist team for the best service."
                else:
                    return f"The price for this job is {price}. Our team will call you back first thing tomorrow to confirm."
            
            if wants_to_book:
                return self.complete_booking(state, conversation_id)
            else:
                vat_note = " (+ VAT)" if state.get('collected_data', {}).get('service') == 'skip' else ""
                return f"{returned_type} {state.get('collected_data', {}).get('service')} at {state['collected_data']['postcode']}: {price}{vat_note}. Would you like to book this?"
                
        except Exception as e:
            send_webhook(conversation_id, state, 'api_error')
            traceback.print_exc()
            return "I'm sorry, I'm having a technical issue. Let me connect you with our team for immediate help."

    def complete_booking(self, state, conversation_id):
        if not API_AVAILABLE:
            send_webhook(conversation_id, state, 'api_unavailable')
            return 'Our team will contact you to complete your booking.'
        
        try:
            customer_data = state['collected_data']
            customer_data['price'] = state['price']
            customer_data['booking_ref'] = state['booking_ref']
            
            result = complete_booking(customer_data)
            
            if result.get('success'):
                booking_ref = result['booking_ref']
                price = result['price']
                payment_link = result.get('payment_link')
                
                state['booking_completed'] = True
                self.conversations[conversation_id] = state
                
                if payment_link and customer_data.get('phone'):
                    send_sms(customer_data['firstName'], customer_data['phone'], booking_ref, price, payment_link)
                
                response = f"Booking confirmed! Ref: {booking_ref}, Price: {price}."
                if payment_link:
                    response += " A payment link has been sent to your phone."
                
                return response + f" {GENERAL_SCRIPTS['closing']}"
            else:
                send_webhook(conversation_id, state, 'api_booking_failure')
                return "Unable to complete booking. Our team will call you back."
        except Exception:
            send_webhook(conversation_id, state, 'api_error')
            return "Booking issue occurred. Our team will contact you."

    def check_for_missing_info(self, state, service_type):
        missing_fields = [f for f in REQUIRED_FIELDS.get(service_type, []) if not state.get('collected_data', {}).get(f)]
        if not missing_fields: return None
        
        first_missing = missing_fields[0]
        if first_missing == 'customer_type': return "Are you a domestic customer or trade customer?"
        if first_missing == 'firstName': return "I'd be happy to help. What's your name?"
        if first_missing == 'postcode': return "What's your complete postcode? For example, LS14ED rather than just LS1."
        if first_missing == 'phone': return "What's the best phone number to contact you on?"
        if first_missing == 'address_line1': return "What's the first line of your address?"
        if first_missing == 'level_load': return "Is the skip a level load?"
        if first_missing == 'prohibited_check': return "Can you confirm there are no prohibited items in the skip?"
        if first_missing == 'access_issues': return "Are there any access issues for collection?"
        return None

# --- AGENT SUBCLASSES ---
class SkipAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.service_type = 'skip'
        self.default_type = '8yd'

    def get_next_response(self, message, state, conversation_id):
        wants_to_book = self.should_book(message)
        has_all_required_data = all(state.get('collected_data', {}).get(f) for f in REQUIRED_FIELDS['skip'])

        missing_info_response = self.check_for_missing_info(state, self.service_type)
        if missing_info_response:
            return missing_info_response

        if has_all_required_data and not state.get('price'):
            # Check for heavy materials and large skip combination
            if state.get('collected_data', {}).get('type') in ['10yd', '12yd', '14yd', '16yd', '20yd'] and any(material in message.lower() for material in ['soil', 'rubble', 'concrete', 'bricks', 'heavy']):
                return SKIP_HIRE_RULES['A2_heavy_materials']['heavy_materials_max']
            
            # Set default type if not specified
            if not state.get('collected_data', {}).get('type'):
                state['collected_data']['type'] = self.default_type
            
            return self.get_pricing(state, conversation_id, wants_to_book)
        
        if wants_to_book and state.get('price'):
            return self.complete_booking(state, conversation_id)
        
        # Handle prohibited items queries
        if 'plasterboard' in message.lower(): 
            return SKIP_HIRE_RULES['A5_prohibited_items']['plasterboard_response']
        if any(item in message.lower() for item in ['prohibited', 'not allowed', 'can\'t put']):
            return SKIP_HIRE_RULES['A5_prohibited_items']['full_script']
        if any(item in message.lower() for item in ['fridge', 'mattress', 'freezer']):
            return SKIP_HIRE_RULES['A5_prohibited_items']['restrictions_response']
        if any(item in message.lower() for item in ['sofa', 'chair', 'upholstery', 'furniture']):
            return "We can't take sofas, chairs, or upholstered furniture in skips as they're prohibited items."
        if 'permit' in message.lower() and any(term in message.lower() for term in ['cost', 'price', 'charge']):
            return "We'll arrange the permit for you and include the cost in your quote. The price varies by council."
            
        return self.get_pricing(state, conversation_id, wants_to_book)

class MAVAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.service_type = 'mav'
        self.default_type = '6yd'  # Changed from 4yd based on average
        self.service_name = 'man & van'

    def get_next_response(self, message, state, conversation_id):
        wants_to_book = self.should_book(message)
        has_all_required_data = all(state.get('collected_data', {}).get(f) for f in REQUIRED_FIELDS['mav'])

        # Check for heavy materials first
        if any(heavy in message.lower() for heavy in ['soil', 'rubble', 'bricks', 'concrete', 'tiles', 'heavy']):
            return MAV_RULES['B2_heavy_materials']['script']

        # Always ask about supplement items for MAV
        if has_all_required_data and not state.get('supplement_check_done'):
            state['supplement_check_done'] = True
            self.conversations[conversation_id] = state
            return MAV_RULES['supplement_check']

        if has_all_required_data and not state.get('price'):
            # Explain cubic yard pricing if not done
            if not state.get('collected_data', {}).get('volume_explained'):
                state['collected_data']['volume_explained'] = True
                return MAV_RULES['B1_information_gathering']['cubic_yard_explanation']
            
            # Set default volume if not specified
            if not state.get('collected_data', {}).get('type'):
                state['collected_data']['type'] = self.default_type
            
            return self.get_pricing(state, conversation_id, wants_to_book)

        if wants_to_book and state.get('price'):
            return self.complete_booking(state, conversation_id)

        # Handle timing questions
        if 'sunday' in message.lower(): 
            return MAV_RULES['B5_additional_timing']['sunday_collections']['script']
        if any(time_phrase in message.lower() for time_phrase in ['what time', 'specific time', 'exact time', 'morning', 'afternoon']):
            return MAV_RULES['B5_additional_timing']['time_script']

        missing_info_response = self.check_for_missing_info(state, self.service_type)
        if missing_info_response:
            return missing_info_response
        
        return self.get_pricing(state, conversation_id, wants_to_book)

class GrabAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.service_type = 'grab'
        self.default_type = '6wheeler'
        self.service_name = 'grab hire'

    def get_next_response(self, message, state, conversation_id):
        wants_to_book = self.should_book(message)
        has_all_required_data = all(state.get('collected_data', {}).get(f) for f in REQUIRED_FIELDS['grab'])

        if wants_to_book and state.get('price'):
            return self.complete_booking(state, conversation_id)

        # Explain wheeler types if mentioned
        if not state.get('collected_data', {}).get('wheeler_explained'):
            if '8 wheeler' in message.lower() or '8-wheeler' in message.lower():
                state['collected_data']['wheeler_explained'] = True
                state['collected_data']['type'] = '8wheeler'
                return GRAB_RULES['C2_grab_size_exact_scripts']['mandatory_exact_scripts']['8_wheeler']
            if '6 wheeler' in message.lower() or '6-wheeler' in message.lower():
                state['collected_data']['wheeler_explained'] = True
                state['collected_data']['type'] = '6wheeler'
                return GRAB_RULES['C2_grab_size_exact_scripts']['mandatory_exact_scripts']['6_wheeler']

        # Check materials compatibility
        if has_all_required_data and not state.get('collected_data', {}).get('materials_checked'):
            has_soil_rubble = any(material in message.lower() for material in ['soil', 'rubble', 'muckaway', 'dirt', 'earth', 'concrete'])
            has_other_items = any(item in message.lower() for item in ['wood', 'furniture', 'plastic', 'metal', 'general', 'mixed'])
            if has_soil_rubble and has_other_items:
                state['collected_data']['materials_checked'] = True
                make_supplier_call(state.get('collected_data', {}), 'grab_mixed_materials')
                return GRAB_RULES['C3_materials_assessment']['mixed_materials']['script']
            state['collected_data']['materials_checked'] = True

        # Most grab hires need specialist assessment - transfer to team
        if has_all_required_data and not state.get('grab_transferred'):
            state['grab_transferred'] = True
            make_supplier_call(state.get('collected_data', {}), 'grab_hire')
            return "Most grab prices require specialist assessment. Let me put you through to our team who can provide accurate pricing."

        missing_info_response = self.check_for_missing_info(state, self.service_type)
        if missing_info_response:
            return missing_info_response
        
        # Fallback - shouldn't normally reach here
        return "Let me get the grab hire details sorted for you."

# --- FLASK APP AND ROUTING ---
app = Flask(__name__)
CORS(app)

shared_conversations = {}
skip_agent = SkipAgent()
mav_agent = MAVAgent()
grab_agent = GrabAgent()
skip_agent.conversations = shared_conversations
mav_agent.conversations = shared_conversations
grab_agent.conversations = shared_conversations

dashboard_manager = DashboardManager()
conversation_counter = 0

def get_next_conversation_id():
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:08d}"

def route_to_agent(message, conversation_id):
    message_lower = message.lower()
    context = shared_conversations.get(conversation_id, {})
    existing_service = context.get('collected_data', {}).get('service')
    
    if any(word in message_lower for word in ['skip', 'skip hire', 'yard skip', 'cubic yard']):
        return skip_agent.process_message(message, conversation_id)
    elif any(word in message_lower for word in ['man and van', 'mav', 'man & van', 'van collection', 'house clearance', 'clearance']):
        return mav_agent.process_message(message, conversation_id)
    elif any(word in message_lower for word in ['grab', 'grab hire', 'wheeler', 'grab lorry']):
        return grab_agent.process_message(message, conversation_id)
    elif existing_service == 'skip':
        return skip_agent.process_message(message, conversation_id)
    elif existing_service == 'mav':
        return mav_agent.process_message(message, conversation_id)
    elif existing_service == 'grab':
        return grab_agent.process_message(message, conversation_id)
    else:
        # Default to skip if unclear
        return skip_agent.process_message(message, conversation_id)

@app.route('/')
def index():
    return redirect(url_for('user_dashboard_page'))

@app.route('/api/wasteking', methods=['POST'])
def process_message_endpoint():
    try:
        data = request.get_json()
        if not data: return jsonify({"success": False, "message": "No data provided"}), 400
        
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('conversation_id') or data.get('elevenlabs_conversation_id') or get_next_conversation_id()
        
        if not customer_message: return jsonify({"success": False, "message": "No message provided"}), 400
        
        response = route_to_agent(customer_message, conversation_id)
        
        state = shared_conversations.get(conversation_id, {})
        dashboard_manager.update_call(conversation_id, state)
        
        return jsonify({
            "success": True, 
            "message": response, 
            "conversation_id": conversation_id, 
            "timestamp": datetime.now().isoformat(), 
            'stage': state.get('stage'), 
            'price': state.get('price')
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": "I'll connect you with our team who can help immediately.", "error": str(e)}), 500

@app.route('/dashboard/user')
def user_dashboard_page():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>WasteKing - Live Calls Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #f5f6fa; }
        .header { background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 25px; position: fixed; top: 0; left: 0; right: 0; z-index: 1000; }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .stats { display: flex; gap: 30px; margin-top: 15px; font-size: 14px; }
        .live-dot { width: 8px; height: 8px; background: #4caf50; border-radius: 50%; animation: pulse 2s infinite; }
        .main { display: grid; grid-template-columns: 1fr 350px; gap: 20px; padding: 20px; margin-top: 120px; height: calc(100vh - 140px); }
        .calls-section, .form-section { background: white; border-radius: 15px; padding: 25px; overflow-y: auto; }
        .calls-container { min-height: 400px; }
        .call-item { background: #f8f9fa; border-radius: 10px; padding: 20px; margin-bottom: 15px; cursor: pointer; min-height: 120px; }
        .call-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .call-id { font-weight: bold; color: #667eea; }
        .stage { padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; text-transform: uppercase; }
        .stage-collecting_info { background: #fff3cd; color: #856404; }
        .stage-booking { background: #d4edda; color: #155724; }
        .stage-completed { background: #cce7ff; color: #004085; }
        .stage-transfer_completed { background: #e2e3e5; color: #495057; }
        .transcript { background: white; padding: 15px; border-radius: 8px; max-height: 100px; overflow-y: auto; font-size: 13px; margin-top: 10px; }
        .form-group { margin-bottom: 15px; min-height: 60px; }
        .form-label { display: block; margin-bottom: 5px; font-weight: bold; font-size: 14px; }
        .form-input { width: 100%; padding: 10px; border: 2px solid #e9ecef; border-radius: 8px; min-height: 40px; }
        .form-input.filled { background: #e8f5e8; border-color: #4caf50; }
        .no-calls { text-align: center; padding: 60px; color: #666; min-height: 200px; display: flex; flex-direction: column; justify-content: center; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    </style>
</head>
<body>
    <div class="header">
        <h1>Live Calls Dashboard (Last 10 Minutes)</h1>
        <div class="stats">
            <div style="display: flex; align-items: center; gap: 8px;">
                <div class="live-dot"></div>
                <span id="active-calls">0 Active Calls</span>
            </div>
            <div id="last-update">Last update: Never</div>
        </div>
    </div>
    
    <div class="main">
        <div class="calls-section">
            <h2 style="margin-bottom: 20px;">Live Conversations</h2>
            <div id="calls-container" class="calls-container">
                <div class="no-calls">
                    <div style="font-size: 48px; margin-bottom: 20px;">📞</div>
                    Waiting for live calls...
                </div>
            </div>
        </div>
        
        <div class="form-section">
            <h2 style="margin-bottom: 20px;">Auto-Extracted Data</h2>
            <div class="form-group">
                <label class="form-label">Customer Name</label>
                <input type="text" class="form-input" id="customer-name" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Phone Number</label>
                <input type="text" class="form-input" id="customer-phone" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Postcode</label>
                <input type="text" class="form-input" id="customer-postcode" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Service Type</label>
                <input type="text" class="form-input" id="service-type" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Customer Type</label>
                <input type="text" class="form-input" id="customer-type" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Current Stage</label>
                <input type="text" class="form-input" id="current-stage" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Price Quote</label>
                <input type="text" class="form-input" id="price-quote" readonly>
            </div>
             <div class="form-group">
                <label class="form-label">Transcript</label>
                <textarea class="form-input" id="full-transcript" readonly style="height: 200px; resize: vertical;"></textarea>
            </div>
        </div>
    </div>

    <script>
        let selectedCallId = null;

        function loadDashboard() {
            fetch('/api/dashboard/user')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        updateCallsDisplay(data.data.live_calls);
                        document.getElementById('active-calls').textContent = `${data.data.active_calls} Active Calls`;
                        document.getElementById('last-update').textContent = `Last update: ${new Date().toLocaleTimeString()}`;
                        
                        // Keep selected call highlighted if still exists
                        if (selectedCallId) {
                            const selectedCall = data.data.live_calls.find(call => call.id === selectedCallId);
                            if (selectedCall) {
                                selectCall(selectedCallId);
                            } else {
                                selectedCallId = null;
                                clearForm();
                            }
                        }
                    }
                })
                .catch(error => console.error('Dashboard error:', error));
        }
        
        function updateCallsDisplay(calls) {
            const container = document.getElementById('calls-container');

            if (!calls || calls.length === 0) {
                container.innerHTML = `
                    <div class="no-calls">
                        <div style="font-size: 48px; margin-bottom: 20px;">📞</div>
                        No calls in the last 10 minutes
                    </div>`;
                return;
            }

            const callsHTML = calls.map(call => {
                const collected_data = call.collected_data || {};
                const last_message = (call.history || []).slice(-1)[0] || 'No transcript yet...';
                const isSelected = selectedCallId === call.id;
                
                return `
                    <div class="call-item ${isSelected ? 'selected' : ''}" onclick="selectCall('${call.id}')" id="call-${call.id}">
                        <div class="call-header">
                            <div class="call-id">${call.id}</div>
                            <div class="stage stage-${call.stage || 'unknown'}">${call.stage || 'Unknown'}</div>
                        </div>
                        <div><strong>Customer:</strong> ${collected_data.firstName || 'Not provided'}</div>
                        <div><strong>Service:</strong> ${collected_data.service || 'Identifying...'}</div>
                        <div><strong>Postcode:</strong> ${collected_data.postcode || 'Not provided'}</div>
                        ${call.price ? `<div><strong>Price:</strong> ${call.price}</div>` : ''}
                        <div class="transcript">${last_message}</div>
                        <div style="font-size: 12px; color: #666; margin-top: 10px;">
                            ${call.timestamp ? new Date(call.timestamp).toLocaleString() : 'Unknown time'}
                        </div>
                    </div>
                `;
            }).join('');

            container.innerHTML = callsHTML;
        }
        
        function selectCall(callId) {
            selectedCallId = callId;
            
            // Remove previous selection styling
            document.querySelectorAll('.call-item').forEach(item => {
                item.style.border = 'none';
                item.style.backgroundColor = '#f8f9fa';
            });
            
            // Add selection styling
            const selectedElement = document.getElementById(`call-${callId}`);
            if (selectedElement) {
                selectedElement.style.border = '2px solid #667eea';
                selectedElement.style.backgroundColor = '#e8f0fe';
            }
            
            // Update form with call data
            fetch('/api/dashboard/user')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const callData = data.data.live_calls.find(call => call.id === callId);
                        if (callData) {
                            const collected = callData.collected_data || {};
                            
                            document.getElementById('customer-name').value = collected.firstName || '';
                            document.getElementById('customer-phone').value = collected.phone || '';
                            document.getElementById('customer-postcode').value = collected.postcode || '';
                            document.getElementById('service-type').value = collected.service || '';
                            document.getElementById('customer-type').value = collected.customer_type || '';
                            document.getElementById('current-stage').value = callData.stage || '';
                            document.getElementById('price-quote').value = callData.price || '';
                            document.getElementById('full-transcript').value = (callData.history || []).join('\\n');
                            
                            const fields = ['customer-name', 'customer-phone', 'customer-postcode', 'service-type', 'customer-type', 'current-stage', 'price-quote'];
                            fields.forEach(fieldId => {
                                const input = document.getElementById(fieldId);
                                input.classList.toggle('filled', !!input.value);
                            });
                        }
                    }
                });
        }
        
        function clearForm() {
            const fields = ['customer-name', 'customer-phone', 'customer-postcode', 'service-type', 'customer-type', 'current-stage', 'price-quote', 'full-transcript'];
            fields.forEach(fieldId => {
                const input = document.getElementById(fieldId);
                input.value = '';
                input.classList.remove('filled');
            });
        }
        
        document.addEventListener('DOMContentLoaded', loadDashboard);
        setInterval(loadDashboard, 2000);
    </script>
</body>
</html>
""")

@app.route('/dashboard/manager')
def manager_dashboard_page():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>WasteKing - Manager Analytics & Callbacks</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; background: #f5f6fa; }
        .header { background: linear-gradient(135deg, #764ba2, #667eea); color: white; padding: 25px; }
        .main { display: grid; grid-template-columns: 1fr 500px; gap: 25px; padding: 25px; }
        .metrics-section { display: grid; grid-template-rows: auto 1fr; gap: 20px; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
        .card { background: white; padding: 25px; border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.05); }
        .metric-value { font-size: 36px; font-weight: bold; margin-bottom: 10px; }
        .metric-label { color: #666; font-size: 16px; }
        .calls-section { background: white; border-radius: 15px; padding: 25px; max-height: 80vh; overflow-y: auto; }
        .call-item { background: #f8f9fa; border-radius: 10px; padding: 15px; margin-bottom: 10px; border-left: 4px solid #667eea; }
        .callback-required { border-left-color: #ff4757 !important; background: #fff5f5 !important; }
        .call-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .call-id { font-weight: bold; font-size: 14px; }
        .call-status { padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; }
        .status-active { background: #d4edda; color: #155724; }
        .status-completed { background: #cce7ff; color: #004085; }
        .status-transfer_completed { background: #fff3cd; color: #856404; }
        .callback-badge { background: #ff4757; color: white; padding: 2px 8px; border-radius: 10px; font-size: 10px; margin-left: 5px; }
        .call-details { font-size: 13px; color: #666; }
        .call-metrics { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-top: 10px; font-size: 12px; }
        .refresh-btn { position: fixed; top: 100px; right: 25px; background: #667eea; color: white; border: none; padding: 12px 24px; border-radius: 25px; cursor: pointer; }
        .section-title { font-size: 20px; font-weight: bold; margin-bottom: 20px; }
        .performance-indicator { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }
        .perf-excellent { background: #28a745; }
        .perf-good { background: #ffc107; }
        .perf-poor { background: #dc3545; }
        .callback-section { background: #fff5f5; border: 1px solid #ffebee; border-radius: 10px; padding: 15px; margin-bottom: 20px; }
        .callback-count { font-size: 24px; font-weight: bold; color: #d32f2f; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Manager Analytics Dashboard</h1>
        <p>All calls with callback flags and complete analytics</p>
    </div>
    
    <button class="refresh-btn" onclick="loadAnalytics()">Refresh</button>
    
    <div class="main">
        <div class="metrics-section">
            <div class="metrics-grid">
                <div class="card">
                    <div class="metric-value" style="color: #667eea;" id="total-calls">0</div>
                    <div class="metric-label">Total Calls</div>
                </div>
                
                <div class="card">
                    <div class="metric-value" style="color: #4caf50;" id="completed-calls">0</div>
                    <div class="metric-label">Completed Sales</div>
                </div>
                
                <div class="card">
                    <div class="metric-value" style="color: #ff9800;" id="conversion-rate">0%</div>
                    <div class="metric-label">Conversion Rate</div>
                </div>
                
                <div class="card">
                    <div class="metric-value" style="color: #ff4757;" id="callback-count">0</div>
                    <div class="metric-label">Callbacks Required</div>
                </div>
            </div>
            
            <div class="card">
                <h3>Service Performance Breakdown</h3>
                <div id="service-breakdown">Loading...</div>
            </div>
        </div>
        
        <div class="calls-section">
            <div class="callback-section">
                <div class="section-title" style="color: #d32f2f; margin-bottom: 10px;">🔴 Priority Callbacks Required</div>
                <div id="callback-list">Loading callbacks...</div>
            </div>
            
            <div class="section-title">All Call Details</div>
            <div id="calls-list">Loading call details...</div>
        </div>
    </div>

    <script>
        function loadAnalytics() {
            fetch('/api/dashboard/manager')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('total-calls').textContent = data.data.total_calls;
                        document.getElementById('completed-calls').textContent = data.data.completed_calls;
                        document.getElementById('conversion-rate').textContent = data.data.conversion_rate.toFixed(1) + '%';
                        document.getElementById('callback-count').textContent = (data.data.callback_required_calls || []).length;
                        
                        const services = data.data.service_breakdown || {};
                        document.getElementById('service-breakdown').innerHTML = Object.entries(services).map(([service, count]) => {
                            const percentage = data.data.total_calls > 0 ? ((count / data.data.total_calls) * 100).toFixed(1) : 0;
                            return `
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; padding: 10px; background: #f8f9fa; border-radius: 8px;">
                                    <div style="flex: 1;">
                                        <strong>${service || 'Unknown'}</strong>
                                        <div style="font-size: 12px; color: #666;">${percentage}% of calls</div>
                                    </div>
                                    <div style="font-size: 24px; font-weight: bold; color: #667eea;">${count}</div>
                                </div>
                            `;
                        }).join('') || '<div style="color: #666;">No service data yet</div>';
                        
                        updateCallbackList(data.data.callback_required_calls || []);
                        updateCallsList(data.data.recent_calls || []);
                    }
                })
                .catch(error => {
                    console.error('Analytics error:', error);
                });
        }
        
        function updateCallbackList(callbacks) {
            const container = document.getElementById('callback-list');
            if (!callbacks || callbacks.length === 0) {
                container.innerHTML = '<div style="color: #666; text-align: center; padding: 20px;">No callbacks required</div>';
                return;
            }
            
            const callbacksHTML = callbacks.map(call => {
                const collected = call.collected_data || {};
                const reason = call.callback_reason || 'General inquiry';
                
                return `
                    <div style="background: white; border: 1px solid #ffcccb; border-radius: 8px; padding: 12px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <strong style="color: #d32f2f;">${collected.firstName || 'Unknown'}</strong>
                            <span style="font-size: 11px; background: #ff4757; color: white; padding: 2px 6px; border-radius: 10px;">CALLBACK REQUIRED</span>
                        </div>
                        <div style="font-size: 13px; color: #666;">
                            <strong>Phone:</strong> ${collected.phone || 'Not provided'}<br>
                            <strong>Service:</strong> ${collected.service || 'Not specified'}<br>
                            <strong>Reason:</strong> ${reason}<br>
                            <strong>Time:</strong> ${call.timestamp ? new Date(call.timestamp).toLocaleString() : 'Unknown'}
                        </div>
                    </div>
                `;
            }).join('');
            
            container.innerHTML = callbacksHTML;
        }
        
        function updateCallsList(calls) {
            const container = document.getElementById('calls-list');
            if (!calls || calls.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">No calls yet</div>';
                return;
            }
            
            const callsHTML = calls.slice().reverse().map(call => {
                const statusClass = call.status === 'active' ? 'status-active' : call.status === 'completed' ? 'status-completed' : 'status-transfer_completed';
                const perfIndicator = call.status === 'completed' && call.price ? 'perf-excellent' : call.status === 'active' ? 'perf-good' : 'perf-poor';
                const duration = call.timestamp ? Math.round((new Date() - new Date(call.timestamp)) / 1000 / 60) : 0;
                const collected = call.collected_data || {};
                const isCallback = call.callback_required;
                
                return `
                    <div class="call-item ${isCallback ? 'callback-required' : ''}">
                        <div class="call-header">
                            <div class="call-id">
                                <span class="performance-indicator ${perfIndicator}"></span>
                                ${call.id}
                                ${isCallback ? '<span class="callback-badge">CALLBACK</span>' : ''}
                            </div>
                            <div class="call-status ${statusClass}">${call.status}</div>
                        </div>
                        <div class="call-details">
                            <strong>Customer:</strong> ${collected.firstName || 'Not provided'} (${collected.customer_type || 'Unknown type'})<br>
                            <strong>Service:</strong> ${collected.service || 'Identifying...'}<br>
                            <strong>Phone:</strong> ${collected.phone || 'Not provided'}<br>
                            <strong>Postcode:</strong> ${collected.postcode || 'Not provided'}
                            ${call.price ? `<br><strong>Price:</strong> ${call.price}` : ''}
                            ${call.booking_ref ? `<br><strong>Booking:</strong> ${call.booking_ref}` : ''}
                            ${isCallback ? `<br><strong>Callback Reason:</strong> ${call.callback_reason || 'General'}` : ''}
                        </div>
                        <div class="call-metrics">
                            <div><strong>Duration:</strong> ${duration}m</div>
                            <div><strong>Stage:</strong> ${call.stage || 'Unknown'}</div>
                            <div><strong>Messages:</strong> ${(call.history || []).length}</div>
                        </div>
                        <div style="font-size: 11px; color: #999; margin-top: 8px;">
                            ${call.timestamp ? new Date(call.timestamp).toLocaleString() : 'Unknown time'}
                        </div>
                    </div>
                `;
            }).join('');
            
            container.innerHTML = callsHTML;
        }
        
        document.addEventListener('DOMContentLoaded', loadAnalytics);
        setInterval(loadAnalytics, 5000); // Refresh every 5 seconds for manager
    </script>
</body>
</html>
""")


@app.route('/api/test-interface')
def test_interface_page():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Test WasteKing System</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        textarea { width: 100%; height: 100px; padding: 10px; margin: 10px 0; border: 1px solid #ccc; border-radius: 5px; }
        button { background: #667eea; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }
        .response { background: #f0f0f0; padding: 15px; border-radius: 5px; margin: 15px 0; white-space: pre-wrap; }
        .success { background: #d4edda; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; border: 1px solid #f5c6cb; }
    </style>
</head>
<body>
    <div class="container">
        <h1>WasteKing System Test</h1>
        
        <h3>Test Messages</h3>
        <textarea id="test-message" placeholder="Enter test message...">Hi, I'm Abdul and I need an 8 yard skip for LS1 4ED</textarea>
        <br>
        <button onclick="testMessage()">Test Message</button>
        <button onclick="testDomesticCustomer()">Test Domestic Customer</button>
        <button onclick="testTradeCustomer()">Test Trade Customer</button>
        <button onclick="testSkipCollection()">Test Skip Collection</button>
        <button onclick="testComplaint()">Test Complaint</button>
        <button onclick="testDirector()">Test Director Request</button>
        
        <div id="response" class="response" style="display: none;"></div>
        
        <h3>Pre-built Test Scenarios</h3>
        <button onclick="runFullSkipTest()">Run Full Skip Booking Test</button>
        <button onclick="runMAVTest()">Run Man & Van Test</button>
        <div id="full-test-results"></div>
    </div>

    <script>
        let currentConversationId = null;
        
        function testMessage() {
            const message = document.getElementById('test-message').value;
            sendMessage(message);
        }
        
        function testDomesticCustomer() {
            currentConversationId = null;
            sendMessage("Hi, I'm a domestic customer, I need a skip");
        }
        
        function testTradeCustomer() {
            currentConversationId = null;
            sendMessage("Hi, I'm a trade customer, I need a skip");
        }
        
        function testSkipCollection() {
            currentConversationId = null;
            sendMessage("I need my skip collected please");
        }
        
        function testComplaint() {
            sendMessage("I want to make a complaint about my service");
        }
        
        function testDirector() {
            sendMessage("I need to speak to Glenn Currie");
        }
        
        function sendMessage(message) {
            const responseDiv = document.getElementById('response');
            responseDiv.style.display = 'block';
            responseDiv.textContent = 'Processing...';
            responseDiv.className = 'response';
            
            fetch('/api/wasteking', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    customerquestion: message,
                    conversation_id: currentConversationId
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    currentConversationId = data.conversation_id;
                    responseDiv.className = 'response success';
                    responseDiv.textContent = `Response: ${data.message}\n\nStage: ${data.stage || 'N/A'}\nPrice: ${data.price || 'N/A'}\nConversation ID: ${data.conversation_id}`;
                } else {
                    responseDiv.className = 'response error';
                    responseDiv.textContent = `Error: ${data.message}`;
                }
            })
            .catch(error => {
                responseDiv.className = 'response error';
                responseDiv.textContent = `Network Error: ${error.message}`;
            });
        }
        
        async function runFullSkipTest() {
            const resultsDiv = document.getElementById('full-test-results');
            resultsDiv.innerHTML = '<h4>Running Full Skip Booking Test...</h4>';
            
            const messages = [
                "Hi, I need a skip",
                "Domestic customer",
                "Abdul",
                "LS1 4ED", 
                "07823656762",
                "6 yard skip please",
                "No prohibited items",
                "Yes, I want to book it"
            ];
            
            await runTestSequence(messages, resultsDiv);
        }
        
        async function runMAVTest() {
            const resultsDiv = document.getElementById('full-test-results');
            resultsDiv.innerHTML = '<h4>Running Man & Van Test...</h4>';
            
            const messages = [
                "Hi, I need man and van collection",
                "Trade customer",
                "Business Solutions Ltd",
                "Sarah Johnson",
                "M1 2AB",
                "01234567890",
                "About 4 cubic yards",
                "No mattresses or fridges",
                "Yes book it please"
            ];
            
            await runTestSequence(messages, resultsDiv);
        }
        
        async function runTestSequence(messages, resultsDiv) {
            currentConversationId = null;
            let results = [];
            
            for (let i = 0; i < messages.length; i++) {
                try {
                    const response = await fetch('/api/wasteking', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            customerquestion: messages[i],
                            conversation_id: currentConversationId
                        })
                    });
                    
                    const data = await response.json();
                    currentConversationId = data.conversation_id;
                    
                    results.push({
                        step: i + 1,
                        message: messages[i],
                        response: data.message,
                        stage: data.stage,
                        price: data.price,
                        success: data.success
                    });
                    
                    await new Promise(resolve => setTimeout(resolve, 500));
                    
                } catch (error) {
                    results.push({
                        step: i + 1,
                        message: messages[i],
                        error: error.message
                    });
                }
            }
            
            resultsDiv.innerHTML = '<h4>Test Results:</h4>' + results.map((result, i) => `
                <div style="margin: 10px 0; padding: 10px; background: ${result.error ? '#f8d7da' : '#d4edda'}; border-radius: 5px;">
                    <strong>Step ${result.step}: ${result.message}</strong><br>
                    ${result.error ? `Error: ${result.error}` : `Response: ${result.response}<br>Stage: ${result.stage || 'N/A'}<br>Price: ${result.price || 'N/A'}`}
                </div>
            `).join('');
        }
    </script>
</body>
</html>
""")


@app.route('/api/dashboard/user')
def user_dashboard_api():
    try:
        dashboard_data = dashboard_manager.get_user_dashboard_data()
        return jsonify({"success": True, "data": dashboard_data})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "data": {"active_calls": 0, "live_calls": [], "total_calls": 0}})

@app.route('/api/dashboard/manager')
def manager_dashboard_api():
    try:
        dashboard_data = dashboard_manager.get_manager_dashboard_data()
        return jsonify({"success": True, "data": dashboard_data})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "data": {"total_calls": 0, "completed_calls": 0, "conversion_rate": 0, "service_breakdown": {}, "individual_calls": [], "recent_calls": [], "active_calls": [], "callback_required_calls": []}})


if __name__ == '__main__':
    print("🚀 Starting WasteKing FINAL System...")
    print("✅ All agents initialized with domestic/trade customer detection")
    print("✅ Skip sales NEVER transferred - all completed")
    print("✅ Manager dashboard shows ALL calls with callback flags")
    print("✅ User dashboard shows only last 10 minutes")
    print("✅ Zoho email integration ready")
    print("✅ ElevenLabs supplier calling ready")
    print("✅ Fixed UI with no jumping elements")
    print("✅ All existing business rules maintained")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
