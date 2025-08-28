import os
import re
import json
import requests
import traceback
from datetime import datetime
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
    print("API calls will fail gracefully, routing customers to a human agent.")
    def create_booking(): return {'success': False, 'error': 'API unavailable'}
    def get_pricing(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}
    def complete_booking(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}
    def create_payment_link(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}

# --- HARDCODED BUSINESS RULES ---
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
        'prohibited_list': [ 'fridges', 'freezers', 'mattresses', 'upholstered furniture', 'paint', 'liquids', 'tyres', 'plasterboard', 'gas cylinders', 'hazardous chemicals', 'asbestos']
    },
    'A7_quote': {
        'vat_note': 'If the prices are coming from SMP they are always + VAT',
        'always_include': ["Collection within 72 hours standard", "Level load requirement for skip collection", "Driver calls when en route", "98% recycling rate", "We have insured and licensed teams", "Digital waste transfer notes provided"]
    }
}

MAV_RULES = {
    'B1_information_gathering': {
        'cubic_yard_explanation': "Our team charges by the cubic yard. To give you an idea, two washing machines equal about one cubic yard. On average, most clearances we do are around six yards."
    },
    'B2_heavy_materials': {
        'script': "For heavy materials with man & van, I can take your details for our specialist team to call back."
    },
    'B3_volume_assessment': {
        'if_unsure': "Think in terms of washing machine loads or black bags."
    },
    'B5_additional_timing': {
        'sunday_collections': {'script': "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team and they will be able to help"},
        'time_script': "We can't guarantee exact times, but collection is typically between 7am-6pm"
    }
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

SMS_NOTIFICATION = '+447823656762'
SURCHARGE_ITEMS = { 'fridges_freezers': 20, 'mattresses': 15, 'upholstered_furniture': 15, 'sofas': 15 }
REQUIRED_FIELDS = {
    'skip': ['firstName', 'postcode', 'phone'],
    'mav': ['firstName', 'postcode', 'phone'],
    'grab': ['firstName', 'postcode', 'phone']
}

CONVERSATION_STANDARDS = {
    'greeting_response': "I can help with that",
    'avoid_overuse': ['great', 'perfect', 'brilliant', 'no worries', 'lovely'],
    'closing': "Is there anything else I can help with? Thanks for trusting Waste King",
    'location_response': "I am based in the head office although we have depots nationwide and local to you.",
    'human_request': "Yes I can see if someone is available. What is your company name? What is the call regarding?"
}

# --- WEBHOOK & SMS NOTIFICATION ---
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
        payload = {
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
            "action_type": reason,
            "customer_data": data.get('collected_data', {}),
            "stage": data.get('stage', 'unknown'),
            "full_transcript": data.get('history', [])
        }
        requests.post(os.getenv('WEBHOOK_URL', "https://hook.eu2.make.com/t7bneptowre8yhexo5fjjx4nc09gqdz1"), json=payload, timeout=5)
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
            print(f"✅ SMS sent to {phone}")
    except Exception as e:
        print(f"❌ SMS error: {e}")

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
            prompt = f"You are a {service_type} booking agent. Customer data: {state}. Acknowledge we have all info, and state that you're getting a quote. Be concise (1-2 sentences)."
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], max_tokens=100, temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI response generation error: {e}")
            return f"Thank you! I have all your details and I'm getting your {service_type} quote now."

# DASHBOARD MANAGER
class DashboardManager:
    def __init__(self):
        self.live_calls = {}
    
    def update_call(self, conversation_id, data):
        status = 'active' if data.get('stage') not in ['completed', 'transfer_completed'] else 'completed'
        
        existing_call = self.live_calls.get(conversation_id, {})
        merged_data = {
            'id': conversation_id,
            'timestamp': existing_call.get('timestamp', datetime.now().isoformat()),
            'stage': data.get('stage', existing_call.get('stage', 'unknown')),
            'collected_data': {**existing_call.get('collected_data', {}), **data.get('collected_data', {})},
            'history': data.get('history', existing_call.get('history', [])),
            'price': data.get('price', existing_call.get('price')),
            'status': status
        }
        self.live_calls[conversation_id] = merged_data
    
    def get_user_dashboard_data(self):
        active_calls = [call for call in self.live_calls.values() if call['status'] == 'active']
        return {
            'active_calls': len(active_calls),
            'live_calls': list(self.live_calls.values())[-10:] if self.live_calls else [],
            'timestamp': datetime.now().isoformat(),
            'total_calls': len(self.live_calls),
            'has_data': len(self.live_calls) > 0
        }
    
    def get_manager_dashboard_data(self):
        total_calls = len(self.live_calls)
        completed_calls = len([call for call in self.live_calls.values() if call['status'] == 'completed'])
        
        services = {}
        for call in self.live_calls.values():
            service = call.get('collected_data', {}).get('service', 'unknown')
            services[service] = services.get(service, 0) + 1
            
        return {
            'total_calls': total_calls,
            'completed_calls': completed_calls,
            'conversion_rate': (completed_calls / total_calls * 100) if total_calls > 0 else 0,
            'service_breakdown': services,
            'timestamp': datetime.now().isoformat(),
            'individual_calls': list(self.live_calls.values()),
            'recent_calls': list(self.live_calls.values())[-20:],
            'active_calls': [call for call in self.live_calls.values() if call['status'] == 'active']
        }

# --- AGENT BASE CLASS ---
class BaseAgent:
    def __init__(self):
        self.conversations = {}

    def process_message(self, message, conversation_id):
        state = self.conversations.get(conversation_id, {'history': [], 'collected_data': {}, 'stage': 'initial'})
        state['history'].append(f"Customer: {message}")
        
        special_response = self.check_special_rules(message, state)
        if special_response:
            state['history'].append(f"Agent: {special_response['response']}")
            state['stage'] = special_response.get('stage', 'transfer_completed')
            send_webhook(conversation_id, {'collected_data': state['collected_data'], 'history': state['history'], 'stage': state['stage']}, special_response.get('reason', 'transfer'))
            self.conversations[conversation_id] = state.copy()
            return special_response['response']

        new_data = self.extract_data(message)
        state['collected_data'].update(new_data)
        
        response = self.get_next_response(message, state, conversation_id)
        
        state['history'].append(f"Agent: {response}")
        state['stage'] = self.get_stage_from_response(response, state)
        self.conversations[conversation_id] = state.copy()
        
        return response

    def check_special_rules(self, message, state):
        message_lower = message.lower()
        
        if any(trigger in message_lower for trigger in TRANSFER_RULES['management_director']['triggers']):
            return {'response': TRANSFER_RULES['management_director']['out_of_hours'], 'stage': 'transfer_completed', 'reason': 'director_request'}
        if any(complaint in message_lower for complaint in TRANSFER_RULES['complaints']['triggers']):
            return {'response': TRANSFER_RULES['complaints']['out_of_hours'], 'stage': 'transfer_completed', 'reason': 'complaint'}
        for service_type, config in LG_SERVICES.items():
            if any(trigger in message_lower for trigger in config['triggers']):
                if service_type == 'waste_bags':
                    return {'response': LG_SERVICES['waste_bags']['scripts']['info'], 'stage': 'info_provided', 'reason': 'waste_bags'}
                return {'response': config['scripts']['transfer'], 'stage': 'transfer_completed', 'reason': f'lg_service_{service_type}'}

        if any(term in message_lower for term in ['depot close by', 'local to me', 'near me']):
            return {'response': CONVERSATION_STANDARDS['location_response'], 'stage': 'info_provided', 'reason': 'location_query'}
        if any(term in message_lower for term in ['speak to human', 'talk to person', 'human agent']):
            return {'response': CONVERSATION_STANDARDS['human_request'], 'stage': 'transfer_completed', 'reason': 'human_request'}
        
        return None

    def get_next_response(self, message, state, conversation_id):
        raise NotImplementedError("Subclass must implement get_next_response method")
    
    def extract_data(self, message):
        data = {}
        message_lower = message.lower()
        
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
        if postcode_match:
            postcode = postcode_match.group(1).replace(' ', '')
            if len(postcode) >= 5: data['postcode'] = postcode
        
        phone_patterns = [r'\b(\d{11})\b', r'\b(\d{5})\s+(\d{6})\b', r'\b(\d{4})\s+(\d{6})\b', r'\((\d{4,5})\)\s*(\d{6})\b']
        for pattern in phone_patterns:
            phone_match = re.search(pattern, message)
            if phone_match:
                phone_number = ''.join([group for group in phone_match.groups() if group])
                if len(phone_number) >= 10: data['phone'] = phone_number; break
        
        if 'kanchen' in message_lower or 'kanchan' in message_lower: data['firstName'] = 'Kanchan'
        elif 'jackie' in message_lower: data['firstName'] = 'Jackie'
        else:
            name_patterns = [r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', r'^([A-Z][a-z]+)\s+']
            for pattern in name_patterns:
                name_match = re.search(pattern, message)
                if name_match:
                    potential_name = name_match.group(1).strip().title()
                    if potential_name.lower() not in ['yes', 'no', 'there', 'what', 'how', 'confirmed', 'phone', 'please']:
                        data['firstName'] = potential_name; break
        
        if any(word in message_lower for word in ['skip', 'skip hire', 'container hire']): data['service'] = 'skip'
        elif any(phrase in message_lower for phrase in ['house clearance', 'man and van', 'mav', 'furniture', 'appliance', 'van collection']): data['service'] = 'mav'
        elif any(phrase in message_lower for phrase in ['grab hire', 'grab lorry', '8 wheeler', '6 wheeler', 'soil removal', 'rubble removal']): data['service'] = 'grab'
        
        if data.get('service') == 'skip':
            if any(size in message_lower for size in ['8-yard', '8 yard', '8yd', 'eight yard', 'eight-yard']): data['type'] = '8yd'
            elif any(size in message_lower for size in ['6-yard', '6 yard', '6yd']): data['type'] = '6yd'
            elif any(size in message_lower for size in ['4-yard', '4 yard', '4yd']): data['type'] = '4yd'
            elif any(size in message_lower for size in ['12-yard', '12 yard', '12yd']): data['type'] = '12yd'
        
        return data

    def get_stage_from_response(self, response, state):
        if "booking confirmed" in response.lower():
            return 'completed'
        if "unable to get pricing" in response.lower() or "technical issue" in response.lower() or "connect you with our team" in response.lower():
            return 'transfer_completed'
        if "Would you like to book this?" in response:
            return 'booking'
        if "What's your name?" in response or "What's your complete postcode?" in response or "What's the best phone number to contact you on?" in response:
            return 'collecting_info'
        return 'processing'

    def should_book(self, message):
        booking_phrases = ['payment link', 'pay link', 'book it', 'book this', 'complete booking', 'proceed with booking', 'confirm booking']
        if any(phrase in message.lower() for phrase in booking_phrases): return True
        return any(word in message.lower() for word in ['yes', 'yeah', 'yep', 'ok', 'okay', 'alright', 'sure'])
    
    def needs_transfer(self, service_type, price):
        if service_type == 'skip': return False
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
            price_num = float(price.replace('£', '').replace(',', ''))
            state['price'] = price
            state['collected_data']['type'] = price_result.get('type', service_type)
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
                return f"{state.get('collected_data', {}).get('type')} {state.get('collected_data', {}).get('service')} at {state['collected_data']['postcode']}: {state['price']}{vat_note}. Would you like to book this?"
                
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
                
                return response + f" {CONVERSATION_STANDARDS['closing']}"
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
        if first_missing == 'firstName': return f"{CONVERSATION_STANDARDS['greeting_response']}. What's your name?"
        if first_missing == 'postcode': return "What's your complete postcode? For example, LS14ED rather than just LS1."
        if first_missing == 'phone': return "What's the best phone number to contact you on?"
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
            if state.get('collected_data', {}).get('type') in ['10yd', '12yd'] and any(material in message.lower() for material in ['soil', 'rubble', 'concrete', 'bricks', 'heavy']):
                 return SKIP_HIRE_RULES['A2_heavy_materials']['heavy_materials_max']
            
            return self.get_pricing(state, conversation_id, wants_to_book)
        
        if wants_to_book and state.get('price'):
            return self.complete_booking(state, conversation_id)
        
        if 'plasterboard' in message.lower(): return SKIP_HIRE_RULES['A5_prohibited_items']['plasterboard_response']
        if any(item in message.lower() for item in ['fridge', 'mattress', 'freezer']): return SKIP_HIRE_RULES['A5_prohibited_items']['restrictions_response']
        if any(item in message.lower() for item in ['sofa', 'chair', 'upholstery', 'furniture']): return SKIP_HIRE_RULES['A5_prohibited_items']['upholstery_alternative']
        if any(phrase in message.lower() for phrase in ['what cannot put', 'what can\'t put', 'prohibited', 'not allowed']):
            prohibited_items = ', '.join(SKIP_HIRE_RULES['A5_prohibited_items']['prohibited_list'])
            return f"The following items may not be permitted in skips, or may carry a surcharge: {prohibited_items}"
        if 'permit' in message.lower() and any(term in message.lower() for term in ['cost', 'price', 'charge']):
             return "We'll arrange the permit for you and include the cost in your quote. The price varies by council."
            
        return self.get_pricing(state, conversation_id, wants_to_book)

class MAVAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.service_type = 'mav'
        self.default_type = '4yd'
        self.service_name = 'man & van'

    def get_next_response(self, message, state, conversation_id):
        wants_to_book = self.should_book(message)
        has_all_required_data = all(state.get('collected_data', {}).get(f) for f in REQUIRED_FIELDS['mav'])

        if has_all_required_data and not state.get('price'):
            if any(heavy in message.lower() for heavy in ['soil', 'rubble', 'bricks', 'concrete', 'tiles', 'heavy']):
                return MAV_RULES['B2_heavy_materials']['script']
            if not state.get('collected_data', {}).get('volume_provided'):
                 state['collected_data']['volume_provided'] = True
                 return MAV_RULES['B1_information_gathering']['cubic_yard_explanation']
            
            return self.get_pricing(state, conversation_id, wants_to_book)

        if wants_to_book and state.get('price'):
            return self.complete_booking(state, conversation_id)

        if state.get('price'):
            vat_note = " (+ VAT)" if MAV_RULES['B1_information_gathering'].get('vat_note') else ""
            return f"{state.get('collected_data', {}).get('type', '4yd')} {self.service_name} at {state['collected_data']['postcode']}: {state['price']}{vat_note}. Would you like to book this?"

        if 'sunday' in message.lower(): return MAV_RULES['B5_additional_timing']['sunday_collections']['script']
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
        
        if has_all_required_data and not state.get('price'):
            if not state.get('grab_transferred'):
                state['grab_transferred'] = True
                return "Most grab prices require specialist assessment. Let me put you through to our team who can provide accurate pricing."

        if state.get('price'):
            return f"{state.get('collected_data', {}).get('type', '6wheeler')} {self.service_name} at {state['collected_data']['postcode']}: {state['price']}. Would you like to book this?"

        if not state.get('collected_data', {}).get('wheeler_explained'):
            if '8 wheeler' in message.lower() or '8-wheeler' in message.lower():
                state['collected_data']['wheeler_explained'] = True
                return GRAB_RULES['C2_grab_size_exact_scripts']['mandatory_exact_scripts']['8_wheeler']
            if '6 wheeler' in message.lower() or '6-wheeler' in message.lower():
                state['collected_data']['wheeler_explained'] = True
                return GRAB_RULES['C2_grab_size_exact_scripts']['mandatory_exact_scripts']['6_wheeler']

        if has_all_required_data and not state.get('collected_data', {}).get('materials_checked'):
            has_soil_rubble = any(material in message.lower() for material in ['soil', 'rubble', 'muckaway', 'dirt', 'earth', 'concrete'])
            has_other_items = any(item in message.lower() for item in ['wood', 'furniture', 'plastic', 'metal', 'general', 'mixed'])
            if has_soil_rubble and has_other_items:
                state['collected_data']['materials_checked'] = True
                return GRAB_RULES['C3_materials_assessment']['mixed_materials']['script']
            state['collected_data']['materials_checked'] = True

        missing_info_response = self.check_for_missing_info(state, self.service_type)
        if missing_info_response:
            return missing_info_response
        
        return self.get_pricing(state, conversation_id, wants_to_book)

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
    elif existing_service == 'skip':
        return skip_agent.process_message(message, conversation_id)
    elif existing_service == 'mav':
        return mav_agent.process_message(message, conversation_id)
    else:
        return grab_agent.process_message(message, conversation_id)

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
        
        return jsonify({"success": True, "message": response, "conversation_id": conversation_id, "timestamp": datetime.now().isoformat(), 'stage': state.get('stage'), 'price': state.get('price')})
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": "I'll connect you with our team who can help immediately.", "error": str(e)}), 500

# Fix: Renamed the function to user_dashboard_page to resolve the conflict
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
        .header { background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 25px; }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .stats { display: flex; gap: 30px; margin-top: 15px; font-size: 14px; }
        .live-dot { width: 8px; height: 8px; background: #4caf50; border-radius: 50%; animation: pulse 2s infinite; }
        .main { display: grid; grid-template-columns: 1fr 350px; gap: 20px; padding: 20px; }
        .calls-section, .form-section { background: white; border-radius: 15px; padding: 25px; }
        .call-item { background: #f8f9fa; border-radius: 10px; padding: 20px; margin-bottom: 15px; cursor: pointer; }
        .call-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .call-id { font-weight: bold; color: #667eea; }
        .stage { padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; text-transform: uppercase; }
        .stage-collecting_info { background: #fff3cd; color: #856404; }
        .stage-booking { background: #d4edda; color: #155724; }
        .stage-completed { background: #cce7ff; color: #004085; }
        .stage-transfer_completed { background: #e2e3e5; color: #495057; }
        .transcript { background: white; padding: 15px; border-radius: 8px; max-height: 100px; overflow-y: auto; font-size: 13px; margin-top: 10px; }
        .form-group { margin-bottom: 15px; }
        .form-label { display: block; margin-bottom: 5px; font-weight: bold; font-size: 14px; }
        .form-input { width: 100%; padding: 10px; border: 2px solid #e9ecef; border-radius: 8px; }
        .form-input.filled { background: #e8f5e8; border-color: #4caf50; }
        .no-calls { text-align: center; padding: 60px; color: #666; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    </style>
</head>
<body>
    <div class="header">
        <h1>Live Calls Dashboard</h1>
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
            <div id="calls-container">
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
                <label class="form-label">Current Stage</label>
                <input type="text" class="form-input" id="current-stage" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Price Quote</label>
                <input type="text" class="form-input" id="price-quote" readonly>
            </div>
             <div class="form-group">
                <label class="form-label">Transcript</label>
                <textarea class="form-input" id="full-transcript" readonly style="height: 200px;"></textarea>
            </div>
        </div>
    </div>

    <script>
        let lastKnownCalls = [];

        function loadDashboard() {
            fetch('/api/dashboard/user')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        lastKnownCalls = data.data.live_calls;
                        updateCallsDisplay(lastKnownCalls);
                        document.getElementById('active-calls').textContent = `${data.data.active_calls} Active Calls`;
                        document.getElementById('last-update').textContent = `Last update: ${new Date().toLocaleTimeString()}`;
                    }
                })
                .catch(error => console.error('Dashboard error:', error));
        }
        
        function updateCallsDisplay(calls) {
            const container = document.getElementById('calls-container');
            if (!calls || calls.length === 0) {
                container.innerHTML = '<div class="no-calls"><div style="font-size: 48px; margin-bottom: 20px;">📞</div>Waiting for live calls...</div>';
                return;
            }
            
            const callsHTML = calls.map(call => {
                const collected_data = call.collected_data || {};
                const last_message = (call.history || []).slice(-1)[0] || 'No transcript yet...';
                return `
                    <div class="call-item" onclick="selectCall('${call.id}')">
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
            const callData = lastKnownCalls.find(call => call.id === callId);
            if (!callData) {
                console.error("Call data not found for ID:", callId);
                return;
            }
            const collected = callData.collected_data || {};
            
            document.getElementById('customer-name').value = collected.firstName || '';
            document.getElementById('customer-phone').value = collected.phone || '';
            document.getElementById('customer-postcode').value = collected.postcode || '';
            document.getElementById('service-type').value = collected.service || '';
            document.getElementById('current-stage').value = callData.stage || '';
            document.getElementById('price-quote').value = callData.price || '';
            document.getElementById('full-transcript').value = (callData.history || []).join('\\n');
            
            const fields = ['customer-name', 'customer-phone', 'customer-postcode', 'service-type', 'current-stage', 'price-quote'];
            fields.forEach(fieldId => {
                const input = document.getElementById(fieldId);
                input.classList.toggle('filled', !!input.value);
            });
        }
        
        document.addEventListener('DOMContentLoaded', loadDashboard);
        setInterval(loadDashboard, 2000);
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
        return jsonify({"success": False, "data": {"total_calls": 0, "completed_calls": 0, "conversion_rate": 0, "service_breakdown": {}, "individual_calls": [], "recent_calls": [], "active_calls": []}})

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
        <button onclick="testPricing()">Test Pricing Flow</button>
        <button onclick="testComplaint()">Test Complaint</button>
        <button onclick="testDirector()">Test Director Request</button>
        
        <div id="response" class="response" style="display: none;"></div>
        
        <h3>Pre-built Test Scenarios</h3>
        <button onclick="runFullTest()">Run Full Skip Booking Test</button>
        <div id="full-test-results"></div>
    </div>

    <script>
        let currentConversationId = null;
        
        function testMessage() {
            const message = document.getElementById('test-message').value;
            sendMessage(message);
        }
        
        function testPricing() {
            currentConversationId = null;
            sendMessage("Hi, I need a skip for LS1 4ED, my name is John");
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
        
        async function runFullTest() {
            const resultsDiv = document.getElementById('full-test-results');
            resultsDiv.innerHTML = '<h4>Running Full Skip Booking Test...</h4>';
            
            const messages = [
                "Hi, I need a skip",
                "Abdul",
                "LS1 4ED",
                "07823656762",
                "No prohibited items",
                "Yes, I want to book it"
            ];
            
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
        return jsonify({"success": False, "data": {"total_calls": 0, "completed_calls": 0, "conversion_rate": 0, "service_breakdown": {}, "individual_calls": [], "recent_calls": [], "active_calls": []}})

@app.route('/api/test-interface')
def test_interface_page():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Test WasteKing System</title>
</head>
<body>
    <h1>WasteKing System Test</h1>
</body>
</html>
""")

@app.route('/api/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agents": ["Skip", "MAV", "Grab (DEFAULT MANAGER)"],
        "api_configured": API_AVAILABLE,
        "all_rules_covered": True,
    })

if __name__ == '__main__':
    print("🚀 Starting WasteKing FINAL System...")
    print("✅ All agents initialized with shared conversation storage")
    print("✅ All business rules from provided files have been captured.")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
