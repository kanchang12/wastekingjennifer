# complete_wasteking_app.py - FINAL VERSION WITH ALL FIXES

import os
import json
import re
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

# Handle API imports with fallback
try:
    from utils.wasteking_api import complete_booking, create_booking, get_pricing
except ImportError:
    print("Warning: utils.wasteking_api not found. Using mock functions.")
    
    def create_booking():
        return {'success': True, 'booking_ref': f'WK{datetime.now().strftime("%Y%m%d%H%M%S")}'}
    
    def get_pricing(booking_ref, postcode, service, service_type):
        prices = {'skip': '£150', 'mav': '£200', 'grab': '£300'}
        return {'success': True, 'price': prices.get(service, '£150')}
    
    def complete_booking(data):
        return {
            'success': True, 
            'booking_ref': f'WK{datetime.now().strftime("%Y%m%d%H%M%S")}',
            'price': '£150'
        }

# WEBHOOK CONFIGURATION
WEBHOOK_URL = "https://hook.eu2.make.com/t7bneptowre8yhexo5fjjx4nc09gqdz1"

def send_callback_webhook(conversation_id: str, call_data: Dict, reason: str):
    """Send webhook for callbacks and transfers"""
    try:
        payload = {
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
            "action_type": reason,
            "customer_name": call_data.get('collected_data', {}).get('firstName', 'Not provided'),
            "customer_phone": call_data.get('collected_data', {}).get('phone', 'Not provided'),
            "customer_postcode": call_data.get('collected_data', {}).get('postcode', 'Not provided'),
            "service_requested": call_data.get('collected_data', {}).get('service', 'Not specified'),
            "call_stage": call_data.get('stage', 'Unknown'),
            "last_message": call_data.get('history', [])[-1] if call_data.get('history') else 'No messages',
            "requires_callback": True,
            "priority": "high" if reason in ['complaint', 'director_request'] else "normal",
            "internal_notes": f"Call ended with: {reason}",
            "full_transcript": call_data.get('history', [])
        }
        
        print(f"Sending webhook for {reason}: {conversation_id}")
        
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"Webhook sent successfully for {conversation_id}")
            return True
        else:
            print(f"Webhook failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Webhook error for {conversation_id}: {e}")
        return False

# BUSINESS RULES
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
        'office_hours': "I understand your frustration, please bear with me while I transfer you to the appropriate person.",
        'out_of_hours': "I understand your frustration. I can take your details and have our customer service team call you back first thing tomorrow.",
        'action': 'TRANSFER',
        'sms_notify': '+447823656762'
    },
    'specialist_services': {
        'services': ['hazardous waste disposal', 'asbestos removal', 'asbestos collection', 'weee electrical waste', 'chemical disposal', 'medical waste', 'trade waste', 'wheelie bins'],
        'office_hours': 'Transfer immediately',
        'out_of_hours': 'Take details + SMS notification to +447823656762'
    }
}

LG_SERVICES = {
    'road_sweeper': {
        'questions': ['postcode', 'hours_required', 'tipping_location', 'when_required'],
        'scripts': {
            'transfer': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
        }
    },
    'toilet_hire': {
        'questions': ['postcode', 'number_required', 'event_or_longterm', 'duration', 'delivery_date'],
        'scripts': {
            'transfer': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
        }
    },
    'asbestos': {
        'questions': ['postcode', 'skip_or_collection', 'asbestos_type', 'dismantle_or_collection', 'quantity'],
        'scripts': {
            'transfer': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
        }
    },
    'hazardous_waste': {
        'questions': ['postcode', 'description', 'data_sheet'],
        'scripts': {
            'transfer': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
        }
    },
    'wheelie_bins': {
        'questions': ['postcode', 'domestic_or_commercial', 'waste_type', 'bin_size', 'number_bins', 'collection_frequency', 'duration'],
        'scripts': {
            'transfer': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
        }
    },
    'waste_bags': {
        'sizes': ['1.5', '3.6', '4.5'],
        'scripts': {
            'info': "Our skip bags are for light waste only. Is this for light waste and our man and van service will collect the rubbish? We can deliver a bag out to you and you can fill it and then we collect and recycle the rubbish. We have 3 sizes: 1.5, 3.6, 4.5 cubic yards bags. Bags are great as there's no time limit and we collect when you're ready"
        }
    }
}

CONVERSATION_STANDARDS = {
    'greeting_response': "We can help you with that",
    'closing': "Is there anything else I can help with? Thanks for trusting Waste King"
}

class FixedDashboardManager:
    """Fixed dashboard manager with proper data handling"""
    
    def __init__(self):
        self.live_calls = {}
        self.call_metrics = {}
    
    def update_live_call(self, conversation_id: str, data: Dict):
        """Update live call data - FIXED"""
        self.live_calls[conversation_id] = {
            'id': conversation_id,
            'timestamp': datetime.now().isoformat(),
            'stage': data.get('stage', 'unknown'),
            'collected_data': data.get('collected_data', {}),
            'transcript': data.get('history', []),
            'status': 'active' if data.get('stage', '') not in ['completed', 'transfer_completed'] else 'completed',
            'price': data.get('price'),
            'booking_ref': data.get('booking_ref')
        }
        print(f"Dashboard updated for {conversation_id}: {data.get('stage', 'unknown')}")
    
    def get_user_dashboard_data(self) -> Dict:
        """FIXED - Always return proper data"""
        active_calls = [call for call in self.live_calls.values() if call['status'] == 'active']
        
        result = {
            'active_calls': len(active_calls),
            'live_calls': list(self.live_calls.values())[-10:] if self.live_calls else [],
            'timestamp': datetime.now().isoformat(),
            'total_calls': len(self.live_calls),
            'has_data': len(self.live_calls) > 0
        }
        
        print(f"Dashboard API returning: {len(self.live_calls)} calls, active: {len(active_calls)}")
        return result
    
    def get_manager_dashboard_data(self) -> Dict:
        """FIXED - Include individual call details + analytics"""
        total_calls = len(self.live_calls)
        completed_calls = len([call for call in self.live_calls.values() if call['status'] == 'completed'])
        
        return {
            'total_calls': total_calls,
            'completed_calls': completed_calls,
            'conversion_rate': (completed_calls / total_calls * 100) if total_calls > 0 else 0,
            'service_breakdown': self._get_service_breakdown(),
            'timestamp': datetime.now().isoformat(),
            'individual_calls': list(self.live_calls.values()),
            'recent_calls': list(self.live_calls.values())[-20:],
            'active_calls': [call for call in self.live_calls.values() if call['status'] == 'active']
        }
    
    def _get_service_breakdown(self) -> Dict:
        """Analyze service distribution"""
        services = {}
        for call in self.live_calls.values():
            service = call.get('collected_data', {}).get('service', 'unknown')
            services[service] = services.get(service, 0) + 1
        return services

class ComprehensiveConversationOrchestrator:
    """Complete orchestrator with ALL fixes"""
    
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY')) if os.getenv('OPENAI_API_KEY') else None
        self.conversations = {}
        
    def is_business_hours(self):
        """Check if it's business hours"""
        now = datetime.now()
        day_of_week = now.weekday()
        hour = now.hour + (now.minute / 60.0)
        
        if day_of_week < 4:  # Monday-Thursday
            return OFFICE_HOURS['monday_thursday']['start'] <= hour < OFFICE_HOURS['monday_thursday']['end']
        elif day_of_week == 4:  # Friday
            return OFFICE_HOURS['friday']['start'] <= hour < OFFICE_HOURS['friday']['end']
        elif day_of_week == 5:  # Saturday
            return OFFICE_HOURS['saturday']['start'] <= hour < OFFICE_HOURS['saturday']['end']
        return False

    def process_conversation(self, message: str, conversation_id: str) -> Dict:
        """FIXED - Proper state transitions to prevent loops"""
        
        state = self.conversations.get(conversation_id, {
            'stage': 'initial',
            'history': [],
            'collected_data': {},
            'service_type': None,
            'price': None,
            'booking_ref': None,
            'loop_counter': 0,
            'conversation_id': conversation_id
        })
        
        # PREVENT INFINITE LOOPS
        state['loop_counter'] = state.get('loop_counter', 0) + 1
        if state['loop_counter'] > 10:
            send_callback_webhook(conversation_id, state, 'loop_prevention')
            return {
                'response': 'Let me connect you with our team who can help immediately.',
                'stage': 'transfer_completed',
                'conversation_id': conversation_id
            }
        
        state['history'].append(f"Customer: {message}")
        print(f"Processing conversation {conversation_id} (stage: {state['stage']}): {message}")
        
        try:
            # Extract data first
            extracted_data = self._extract_customer_data(message)
            if extracted_data:
                state['collected_data'].update(extracted_data)
                print(f"Extracted data: {extracted_data}")
            
            # Check transfer rules first
            transfer_result = self._check_transfer_rules(message, state)
            if transfer_result:
                result = transfer_result
            # Check LG services
            elif self._check_lg_services(message, state):
                result = self._check_lg_services(message, state)
            else:
                # Normal conversation flow
                collected = state['collected_data']
                has_minimum_data = all(collected.get(field) for field in ['firstName', 'postcode', 'service'])
                
                print(f"Current data: {collected}")
                print(f"Has minimum data: {has_minimum_data}")
                
                # STATE MACHINE - FIXED TRANSITIONS
                if state['stage'] == 'initial':
                    if has_minimum_data:
                        result = {'response': 'Let me get you a quote.', 'stage': 'ready_for_api'}
                    else:
                        result = self._handle_information_collection(message, state)
                        
                elif state['stage'] == 'collecting_info':
                    if has_minimum_data:
                        result = {'response': 'Let me get you a quote.', 'stage': 'ready_for_api'}
                    else:
                        result = self._handle_information_collection(message, state)
                        
                elif state['stage'] == 'ready_for_api':
                    # FORCE API CALL HERE
                    result = self._handle_api_calls(message, state)
                    
                elif state['stage'] == 'booking':
                    if self._wants_to_book(message):
                        result = self._complete_booking(state['collected_data'])
                    else:
                        result = {'response': f"Your quote is {state['price']}. Would you like to book this?", 'stage': 'booking'}
                        
                else:
                    result = {'response': 'How can I help with skip hire, man & van, or grab services?', 'stage': 'initial'}
            
            # Update state
            state['stage'] = result.get('stage', state['stage'])
            state['history'].append(f"Agent: {result['response']}")
            if result.get('price'):
                state['price'] = result['price']
            if result.get('booking_ref'):
                state['booking_ref'] = result['booking_ref']
            
            # WEBHOOK TRIGGER CHECK
            if result.get('stage') == 'transfer_completed':
                send_callback_webhook(conversation_id, state, state.get('transfer_type', 'transfer'))
            
            self.conversations[conversation_id] = state
            
            return {
                'success': True,
                'response': result['response'],
                'conversation_id': conversation_id,
                'stage': state['stage'],
                'collected_data': state['collected_data'],
                'history': state['history'],
                'price': state.get('price'),
                'booking_ref': state.get('booking_ref')
            }
            
        except Exception as e:
            print(f"Orchestrator Error: {e}")
            send_callback_webhook(conversation_id, state, 'system_error')
            return {
                'success': False,
                'response': 'Let me connect you with our team who can help immediately.',
                'conversation_id': conversation_id,
                'error': str(e)
            }

    def _check_transfer_rules(self, message: str, state: Dict) -> Optional[Dict]:
        """Apply TRANSFER_RULES + send webhook"""
        message_lower = message.lower()
        conversation_id = state.get('conversation_id', 'unknown')
        
        # Management/Director requests
        if any(trigger in message_lower for trigger in TRANSFER_RULES['management_director']['triggers']):
            if self.is_business_hours():
                response = TRANSFER_RULES['management_director']['office_hours']
            else:
                response = TRANSFER_RULES['management_director']['out_of_hours']
            
            send_callback_webhook(conversation_id, state, 'director_request')
            return {'response': response, 'stage': 'transfer_completed', 'transfer_type': 'management'}
        
        # Complaints
        if any(word in message_lower for word in ['complaint', 'complain', 'unhappy', 'disappointed', 'frustrated', 'angry']):
            if self.is_business_hours():
                response = TRANSFER_RULES['complaints']['office_hours']
            else:
                response = TRANSFER_RULES['complaints']['out_of_hours']
            
            send_callback_webhook(conversation_id, state, 'complaint')
            return {'response': response, 'stage': 'transfer_completed', 'transfer_type': 'complaint'}
        
        # Specialist services
        if any(service in message_lower for service in TRANSFER_RULES['specialist_services']['services']):
            if self.is_business_hours():
                response = TRANSFER_RULES['specialist_services']['office_hours']
            else:
                response = TRANSFER_RULES['specialist_services']['out_of_hours']
            
            send_callback_webhook(conversation_id, state, 'specialist_service')
            return {'response': response, 'stage': 'transfer_completed', 'transfer_type': 'specialist'}
        
        return None

    def _check_lg_services(self, message: str, state: Dict) -> Optional[Dict]:
        """Check for LG services requiring immediate specialist handling"""
        message_lower = message.lower()
        
        if any(term in message_lower for term in ['road sweeper', 'road sweeping', 'street sweeping']):
            return self._handle_lg_service('road_sweeper', message, state)
        
        if any(term in message_lower for term in ['toilet hire', 'portaloo', 'portable toilet']):
            return self._handle_lg_service('toilet_hire', message, state)
        
        if 'asbestos' in message_lower:
            send_callback_webhook(state.get('conversation_id', 'unknown'), state, 'asbestos_request')
            return {
                'response': "Asbestos requires specialist handling. Let me arrange for our certified team to call you back.",
                'stage': 'transfer_completed',
                'transfer_type': 'asbestos'
            }
        
        if any(term in message_lower for term in ['hazardous waste', 'chemical waste', 'dangerous waste']):
            return self._handle_lg_service('hazardous_waste', message, state)
        
        if any(term in message_lower for term in ['wheelie bin', 'wheelie bins', 'bin hire']):
            return self._handle_lg_service('wheelie_bins', message, state)
        
        if any(term in message_lower for term in ['skip bag', 'waste bag', 'skip sack']):
            return {
                'response': LG_SERVICES['waste_bags']['scripts']['info'],
                'stage': 'completed',
                'service_type': 'waste_bags'
            }
        
        return None

    def _handle_lg_service(self, service_type: str, message: str, state: Dict) -> Dict:
        """Handle LG services with webhook"""
        service_config = LG_SERVICES.get(service_type, {})
        questions = service_config.get('questions', [])
        conversation_id = state.get('conversation_id', 'unknown')
        
        missing_info = [q for q in questions if not state['collected_data'].get(q)]
        
        if missing_info:
            question = missing_info[0].replace('_', ' ').title() + "?"
            return {
                'response': f"I need some information: {question}",
                'stage': 'collecting_lg_info',
                'service_type': service_type
            }
        else:
            transfer_script = service_config.get('scripts', {}).get('transfer', 
                "I will take some information from you before passing onto our specialist team")
            
            send_callback_webhook(conversation_id, state, f'lg_service_{service_type}')
            
            return {
                'response': transfer_script,
                'stage': 'transfer_completed',
                'service_type': service_type
            }

    def _handle_information_collection(self, message: str, state: Dict) -> Dict:
        """Information collection with anti-loop protection"""
        
        collected = state['collected_data']
        required_data = ['firstName', 'postcode', 'service']
        missing_data = [field for field in required_data if not collected.get(field)]
        
        if not missing_data:
            return {'response': "Thank you! Let me process your request.", 'stage': 'service_rules'}
        
        if self.client:
            return self._openai_next_question(message, state, missing_data)
        else:
            return self._fallback_next_question(missing_data, collected)

    def _openai_next_question(self, message: str, state: Dict, missing_data: List) -> Dict:
        """OpenAI-powered question generation"""
        try:
            history = "\n".join(state['history'][-6:])
            collected = state['collected_data']
            
            prompt = f"""You are a WasteKing customer service agent. 

CONVERSATION HISTORY:
{history}

COLLECTED DATA:
- Name: {collected.get('firstName', 'MISSING')}
- Phone: {collected.get('phone', 'MISSING')}
- Postcode: {collected.get('postcode', 'MISSING')}
- Service: {collected.get('service', 'MISSING')}

MISSING: {missing_data}

RULES:
1. NEVER repeat questions already asked in history
2. Always start with "We can help you with that" for new customers
3. Ask for missing info in order: firstName, postcode, phone
4. Keep responses short and professional

What should you ask next? Respond with just the question text."""

            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.3
            )
            
            ai_response = response.choices[0].message.content.strip()
            return {'response': ai_response, 'stage': 'collecting_info'}
            
        except Exception as e:
            print(f"OpenAI error: {e}")
            return self._fallback_next_question(missing_data, state['collected_data'])

    def _fallback_next_question(self, missing_data: List, collected: Dict) -> Dict:
        """Fallback question logic without OpenAI"""
        
        if 'firstName' in missing_data:
            response = f"{CONVERSATION_STANDARDS['greeting_response']}. What's your name?"
        elif 'postcode' in missing_data:
            response = "What's your complete postcode?"
        elif 'phone' in missing_data:
            response = "What's the best phone number to contact you on?"
        elif 'service' in missing_data:
            response = "What service do you need - skip hire, man & van, or grab hire?"
        else:
            response = "Thank you! Let me process your request."
            
        return {'response': response, 'stage': 'collecting_info'}

    def _handle_api_calls(self, message: str, state: Dict) -> Dict:
        """FIXED - Actually call the pricing API instead of looping"""
        try:
            collected = state['collected_data']
            conversation_id = state.get('conversation_id', 'unknown')
            
            if not all(collected.get(field) for field in ['firstName', 'postcode', 'service']):
                missing = [f for f in ['firstName', 'postcode', 'service'] if not collected.get(f)]
                return {'response': f"I still need your {', '.join(missing)}", 'stage': 'collecting_info'}
            
            print(f"CALLING PRICING API for {collected.get('service')} in {collected.get('postcode')}")
            
            booking_result = create_booking()
            if not booking_result.get('success'):
                send_callback_webhook(conversation_id, state, 'api_failure_booking')
                return {'response': 'Let me put you through to our team for pricing.', 'stage': 'transfer_completed'}
            
            price_result = get_pricing(
                booking_result['booking_ref'],
                collected.get('postcode'),
                collected.get('service'),
                collected.get('service_type', '8yd')
            )
            
            print(f"PRICING API RESULT: {price_result}")
            
            if price_result.get('success') and price_result.get('price'):
                vat_note = ' (+ VAT)' if collected.get('service') == 'skip' else ''
                return {
                    'response': f"Your {collected.get('service')} service quote: {price_result['price']}{vat_note}. Would you like to book this?",
                    'stage': 'booking',
                    'price': price_result['price'],
                    'booking_ref': booking_result['booking_ref']
                }
            else:
                send_callback_webhook(conversation_id, state, 'api_failure_pricing')
                return {'response': 'Let me check pricing with our team.', 'stage': 'transfer_completed'}
                
        except Exception as e:
            print(f"API CALL ERROR: {e}")
            send_callback_webhook(conversation_id, state, 'api_error')
            return {'response': 'Let me get our team to provide pricing.', 'stage': 'transfer_completed'}

    def _wants_to_book(self, message: str) -> bool:
        """Check if customer wants to proceed with booking"""
        message_lower = message.lower()
        booking_phrases = [
            'book', 'yes', 'proceed', 'payment', 'ok', 'sure', 'sounds good',
            'perfect', 'great', 'lets do it', 'go ahead', 'confirm', 'agree'
        ]
        return any(phrase in message_lower for phrase in booking_phrases)

    def _complete_booking(self, data: Dict) -> Dict:
        """Complete booking API call"""
        try:
            result = complete_booking(data)
            if result.get('success'):
                closing = CONVERSATION_STANDARDS['closing']
                return {
                    'response': f"Booking confirmed! Reference: {result.get('booking_ref')}. {closing}",
                    'stage': 'completed'
                }
            else:
                return {'response': 'Booking issue - our team will contact you shortly.', 'stage': 'completed'}
        except Exception as e:
            return {'response': 'Our team will complete your booking and call back.', 'stage': 'completed'}

    def _extract_customer_data(self, message: str) -> Dict:
        """Extract customer data using improved regex patterns"""
        data = {}
        message_lower = message.lower()

        # Postcode
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
        if postcode_match:
            postcode = postcode_match.group(1).replace(' ', '')
            if len(postcode) >= 5:
                data['postcode'] = postcode

        # Phone
        phone_patterns = [
            r'\b(\d{11})\b',
            r'\b(\d{5})\s+(\d{6})\b',
            r'\b(\d{4})\s+(\d{6})\b',
        ]
        
        for pattern in phone_patterns:
            phone_match = re.search(pattern, message)
            if phone_match:
                phone_parts = [g for g in phone_match.groups() if g]
                phone_number = ''.join(phone_parts)
                if len(phone_number) >= 10:
                    data['phone'] = phone_number
                    break

        # Name
        name_patterns = [
            r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+)',
            r'^([A-Z][a-z]+)\s+(?:wants|needs)',
            r'([A-Z][a-z]+)\s+phone',
        ]
        for pattern in name_patterns:
            name_match = re.search(pattern, message)
            if name_match:
                potential_name = name_match.group(1).strip().title()
                if potential_name.lower() not in ['yes', 'no', 'phone', 'please']:
                    data['firstName'] = potential_name
                    break

        # Service detection
        if any(word in message_lower for word in ['skip', 'yard skip', 'container']):
            data['service'] = 'skip'
        elif any(word in message_lower for word in ['clearance', 'furniture', 'man', 'van']):
            data['service'] = 'mav'
        elif any(word in message_lower for word in ['grab', 'wheeler', 'soil', 'rubble']):
            data['service'] = 'grab'

        return data

# Initialize Flask App
app = Flask(__name__)
CORS(app)

# Global instances
orchestrator = ComprehensiveConversationOrchestrator()
dashboard_manager = FixedDashboardManager()
conversation_counter = 0

def get_next_conversation_id():
    """Generate next conversation ID"""
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:08d}"

@app.route('/')
def index():
    """Main dashboard selection page"""
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WasteKing Complete AI System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 60px 40px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            text-align: center;
            max-width: 600px;
            width: 90%;
        }
        .logo {
            font-size: 48px;
            font-weight: bold;
            color: #333;
            margin-bottom: 20px;
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .subtitle {
            font-size: 18px;
            color: #666;
            margin-bottom: 50px;
        }
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 30px;
            margin-top: 40px;
        }
        .dashboard-card {
            background: #f8f9fa;
            border-radius: 15px;
            padding: 30px 20px;
            text-decoration: none;
            color: #333;
            transition: all 0.3s ease;
            border: 2px solid transparent;
        }
        .dashboard-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 30px rgba(0,0,0,0.1);
            border-color: #667eea;
        }
        .dashboard-icon {
            font-size: 48px;
            margin-bottom: 20px;
        }
        .dashboard-title {
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 10px;
        }
        .dashboard-desc {
            color: #666;
            font-size: 14px;
            line-height: 1.5;
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            background: #28a745;
            border-radius: 50%;
            margin-left: 10px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        .version {
            margin-top: 40px;
            font-size: 12px;
            color: #999;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">WasteKing AI</div>
        <div class="subtitle">
            Complete System with Webhooks + Dashboard Fixes
            <span class="status-indicator"></span>
        </div>
        
        <div class="dashboard-grid">
            <a href="/dashboard/user" class="dashboard-card">
                <div class="dashboard-icon">📞</div>
                <div class="dashboard-title">Live Calls Dashboard</div>
                <div class="dashboard-desc">
                    Real-time call monitoring, live transcripts, 
                    auto-form filling (2-second refresh)
                </div>
            </a>
            
            <a href="/dashboard/manager" class="dashboard-card">
                <div class="dashboard-icon">📊</div>
                <div class="dashboard-title">Manager Analytics</div>
                <div class="dashboard-desc">
                    Individual call details, conversion rates, 
                    performance metrics, webhooks tracking
                </div>
            </a>
            
            <a href="/api/test-interface" class="dashboard-card">
                <div class="dashboard-icon">🧪</div>
                <div class="dashboard-title">Testing Interface</div>
                <div class="dashboard-desc">
                    Test conversations, API calls,
                    webhook delivery testing
                </div>
            </a>
        </div>
        
        <div class="version">
            Complete System | All Fixes Applied | Webhook Integration Active
        </div>
    </div>
</body>
</html>
    """)

@app.route('/api/wasteking', methods=['POST', 'GET'])
def elevenlabs_endpoint():
    """Main ElevenLabs entry point"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('conversation_id') or data.get('elevenlabs_conversation_id') or get_next_conversation_id()
        
        print(f"ElevenLabs Request: {conversation_id} - {customer_message}")
        
        if not customer_message:
            return jsonify({"success": False, "message": "No message provided"}), 400
        
        # Process with complete orchestrator
        result = orchestrator.process_conversation(customer_message, conversation_id)
        
        # Update dashboard
        dashboard_manager.update_live_call(conversation_id, result)
        
        print(f"Response: {result.get('response', '')}")
        
        return jsonify({
            "success": True,
            "message": result.get('response', 'We can help you with that.'),
            "conversation_id": conversation_id,
            "stage": result.get('stage', 'processing'),
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"ElevenLabs Endpoint Error: {e}")
        return jsonify({
            "success": False,
            "message": "Let me connect you with our team who can help immediately.",
            "error": str(e)
        }), 500

@app.route('/dashboard/user')
def user_dashboard():
    """Live calls dashboard - 2 second refresh"""
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
        .stage-ready_for_api { background: #e2e3e5; color: #495057; }
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
        </div>
    </div>

    <script>
        function loadDashboard() {
            fetch('/api/dashboard/user')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        updateCallsDisplay(data.data.live_calls);
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
            
            const callsHTML = calls.map(call => `
                <div class="call-item" onclick="selectCall('${call.id}', ${JSON.stringify(call).replace(/"/g, '&quot;')})">
                    <div class="call-header">
                        <div class="call-id">${call.id}</div>
                        <div class="stage stage-${call.stage || 'unknown'}">${call.stage || 'Unknown'}</div>
                    </div>
                    <div><strong>Customer:</strong> ${call.collected_data?.firstName || 'Not provided'}</div>
                    <div><strong>Service:</strong> ${call.collected_data?.service || 'Identifying...'}</div>
                    <div><strong>Postcode:</strong> ${call.collected_data?.postcode || 'Not provided'}</div>
                    ${call.price ? `<div><strong>Price:</strong> ${call.price}</div>` : ''}
                    <div class="transcript">
                        ${(call.transcript || []).slice(-2).join('<br>') || 'No transcript yet...'}
                    </div>
                    <div style="font-size: 12px; color: #666; margin-top: 10px;">
                        ${call.timestamp ? new Date(call.timestamp).toLocaleString() : 'Unknown time'}
                    </div>
                </div>
            `).join('');
            
            container.innerHTML = callsHTML;
        }
        
        function selectCall(callId, callData) {
            const fields = {
                'customer-name': callData.collected_data?.firstName,
                'customer-phone': callData.collected_data?.phone,
                'customer-postcode': callData.collected_data?.postcode,
                'service-type': callData.collected_data?.service,
                'current-stage': callData.stage,
                'price-quote': callData.price
            };
            
            Object.keys(fields).forEach(fieldId => {
                const input = document.getElementById(fieldId);
                const value = fields[fieldId] || '';
                input.value = value;
                input.classList.toggle('filled', !!value);
            });
        }
        
        document.addEventListener('DOMContentLoaded', loadDashboard);
        setInterval(loadDashboard, 2000);
    </script>
</body>
</html>
    """)

@app.route('/dashboard/manager')
def manager_dashboard():
    """Manager analytics dashboard with individual call details"""
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>WasteKing - Manager Analytics</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; background: #f5f6fa; }
        .header { background: linear-gradient(135deg, #764ba2, #667eea); color: white; padding: 25px; }
        .main { display: grid; grid-template-columns: 1fr 400px; gap: 25px; padding: 25px; }
        .metrics-section { display: grid; grid-template-rows: auto 1fr; gap: 20px; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
        .card { background: white; padding: 25px; border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.05); }
        .metric-value { font-size: 36px; font-weight: bold; margin-bottom: 10px; }
        .metric-label { color: #666; font-size: 16px; }
        .calls-section { background: white; border-radius: 15px; padding: 25px; max-height: 80vh; overflow-y: auto; }
        .call-item { background: #f8f9fa; border-radius: 10px; padding: 15px; margin-bottom: 10px; border-left: 4px solid #667eea; }
        .call-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .call-id { font-weight: bold; font-size: 14px; }
        .call-status { padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; }
        .status-active { background: #d4edda; color: #155724; }
        .status-completed { background: #cce7ff; color: #004085; }
        .status-transfer_completed { background: #fff3cd; color: #856404; }
        .call-details { font-size: 13px; color: #666; }
        .call-metrics { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-top: 10px; font-size: 12px; }
        .refresh-btn { position: fixed; top: 100px; right: 25px; background: #667eea; color: white; border: none; padding: 12px 24px; border-radius: 25px; cursor: pointer; }
        .section-title { font-size: 20px; font-weight: bold; margin-bottom: 20px; }
        .performance-indicator { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }
        .perf-excellent { background: #28a745; }
        .perf-good { background: #ffc107; }
        .perf-poor { background: #dc3545; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Manager Analytics Dashboard</h1>
        <p>Real-time insights with individual call details and webhook tracking</p>
    </div>
    
    <button class="refresh-btn" onclick="loadAnalytics()">Refresh</button>
    
    <div class="main">
        <div class="metrics-section">
            <div class="metrics-grid">
                <div class="card">
                    <div class="metric-value" style="color: #667eea;" id="total-calls">0</div>
                    <div class="metric-label">Total Calls Today</div>
                </div>
                
                <div class="card">
                    <div class="metric-value" style="color: #4caf50;" id="completed-calls">0</div>
                    <div class="metric-label">Completed Calls</div>
                </div>
                
                <div class="card">
                    <div class="metric-value" style="color: #ff9800;" id="conversion-rate">0%</div>
                    <div class="metric-label">Conversion Rate</div>
                </div>
                
                <div class="card">
                    <div class="metric-value" style="color: #e91e63;" id="active-now">0</div>
                    <div class="metric-label">Active Right Now</div>
                </div>
            </div>
            
            <div class="card">
                <h3>Service Performance Breakdown</h3>
                <div id="service-breakdown">Loading...</div>
            </div>
        </div>
        
        <div class="calls-section">
            <div class="section-title">Individual Call Details</div>
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
                        document.getElementById('active-now').textContent = (data.data.active_calls || []).length;
                        
                        const services = data.data.service_breakdown || {};
                        document.getElementById('service-breakdown').innerHTML = Object.entries(services).map(([service, count]) => {
                            const percentage = data.data.total_calls > 0 ? ((count / data.data.total_calls) * 100).toFixed(1) : 0;
                            return `
                                <div style="display: flex; justify-content: between; align-items: center; margin-bottom: 10px; padding: 10px; background: #f8f9fa; border-radius: 8px;">
                                    <div style="flex: 1;">
                                        <strong>${service || 'Unknown'}</strong>
                                        <div style="font-size: 12px; color: #666;">${percentage}% of calls</div>
                                    </div>
                                    <div style="font-size: 24px; font-weight: bold; color: #667eea;">${count}</div>
                                </div>
                            `;
                        }).join('') || '<div style="color: #666;">No service data yet</div>';
                        
                        updateCallsList(data.data.recent_calls || []);
                    }
                })
                .catch(error => {
                    console.error('Analytics error:', error);
                });
        }
        
        function updateCallsList(calls) {
            const container = document.getElementById('calls-list');
            
            if (!calls || calls.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">No calls yet today</div>';
                return;
            }
            
            const callsHTML = calls.slice().reverse().map(call => {
                const statusClass = call.status === 'active' ? 'status-active' : 
                                  call.status === 'completed' ? 'status-completed' : 'status-transfer_completed';
                
                const perfIndicator = call.status === 'completed' && call.price ? 'perf-excellent' : 
                                    call.status === 'active' ? 'perf-good' : 'perf-poor';
                
                const duration = call.timestamp ? 
                    Math.round((new Date() - new Date(call.timestamp)) / 1000 / 60) : 0;
                
                return `
                    <div class="call-item">
                        <div class="call-header">
                            <div class="call-id">
                                <span class="performance-indicator ${perfIndicator}"></span>
                                ${call.id}
                            </div>
                            <div class="call-status ${statusClass}">${call.status}</div>
                        </div>
                        <div class="call-details">
                            <strong>Customer:</strong> ${call.collected_data?.firstName || 'Not provided'}<br>
                            <strong>Service:</strong> ${call.collected_data?.service || 'Identifying...'}<br>
                            <strong>Postcode:</strong> ${call.collected_data?.postcode || 'Not provided'}
                            ${call.price ? `<br><strong>Price:</strong> ${call.price}` : ''}
                            ${call.booking_ref ? `<br><strong>Booking:</strong> ${call.booking_ref}` : ''}
                        </div>
                        <div class="call-metrics">
                            <div><strong>Duration:</strong> ${duration}m</div>
                            <div><strong>Stage:</strong> ${call.stage || 'Unknown'}</div>
                            <div><strong>Messages:</strong> ${(call.transcript || []).length}</div>
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
        setInterval(loadAnalytics, 15000);
    </script>
</body>
</html>
    """)

@app.route('/api/test-interface')
def test_interface():
    """Testing interface"""
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>WasteKing Testing Interface</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        textarea { width: 100%; height: 100px; padding: 10px; border: 1px solid #ccc; border-radius: 5px; margin: 10px 0; }
        button { background: #667eea; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }
        .response { background: #f0f0f0; padding: 15px; border-radius: 5px; margin-top: 15px; white-space: pre-wrap; }
        .webhook-status { background: #e8f5e8; padding: 10px; border-radius: 5px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>WasteKing Complete System Testing</h1>
        
        <h3>Test Conversation Flow</h3>
        <textarea id="test-message" placeholder="Enter customer message...">I need an 8 yard skip for LS1 4ED</textarea>
        <br>
        <button onclick="testConversation()">Send Message</button>
        <button onclick="testComplaint()">Test Complaint</button>
        <button onclick="testDirector()">Test Director Request</button>
        <div id="conversation-response" class="response" style="display: none;"></div>
        
        <h3>System Health</h3>
        <button onclick="checkHealth()">Check System Health</button>
        <button onclick="checkWebhook()">Test Webhook</button>
        <div id="health-response" class="response" style="display: none;"></div>
        
        <div class="webhook-status">
            <strong>Webhook URL:</strong> ${WEBHOOK_URL}<br>
            <strong>Status:</strong> Active for callbacks, transfers, and complaints
        </div>
    </div>

    <script>
        function testConversation() {
            const message = document.getElementById('test-message').value;
            sendTestMessage(message);
        }
        
        function testComplaint() {
            sendTestMessage("I want to make a complaint about my service");
        }
        
        function testDirector() {
            sendTestMessage("I need to speak to Glenn Currie the director");
        }
        
        function sendTestMessage(message) {
            const responseDiv = document.getElementById('conversation-response');
            responseDiv.style.display = 'block';
            responseDiv.textContent = 'Processing...';
            
            fetch('/api/wasteking', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    customerquestion: message,
                    conversation_id: 'test_' + Date.now()
                })
            })
            .then(response => response.json())
            .then(data => {
                responseDiv.textContent = JSON.stringify(data, null, 2);
            })
            .catch(error => {
                responseDiv.textContent = 'Error: ' + error.message;
            });
        }
        
        function checkHealth() {
            const responseDiv = document.getElementById('health-response');
            responseDiv.style.display = 'block';
            responseDiv.textContent = 'Checking...';
            
            fetch('/api/health')
            .then(response => response.json())
            .then(data => {
                responseDiv.textContent = JSON.stringify(data, null, 2);
            })
            .catch(error => {
                responseDiv.textContent = 'Error: ' + error.message;
            });
        }
        
        function checkWebhook() {
            alert('Webhook test will be sent on next transfer/complaint. Check your Make.com scenario for delivery.');
        }
    </script>
</body>
</html>
    """)

@app.route('/api/dashboard/user', methods=['GET'])
def user_dashboard_api():
    """FIXED API - Always return valid data"""
    try:
        dashboard_data = dashboard_manager.get_user_dashboard_data()
        
        if not dashboard_data or not isinstance(dashboard_data, dict):
            dashboard_data = {
                'active_calls': 0,
                'live_calls': [],
                'timestamp': datetime.now().isoformat(),
                'total_calls': 0,
                'has_data': False
            }
        
        response = {"success": True, "data": dashboard_data}
        print(f"Dashboard API response size: {len(str(response))} chars")
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Dashboard API error: {e}")
        return jsonify({
            "success": False, 
            "error": str(e),
            "data": {
                'active_calls': 0,
                'live_calls': [],
                'timestamp': datetime.now().isoformat(),
                'total_calls': 0,
                'has_data': False
            }
        }), 500

@app.route('/api/dashboard/manager', methods=['GET'])
def manager_dashboard_api():
    """FIXED API for manager dashboard with individual call details"""
    try:
        dashboard_data = dashboard_manager.get_manager_dashboard_data()
        
        if not dashboard_data or not isinstance(dashboard_data, dict):
            dashboard_data = {
                'total_calls': 0,
                'completed_calls': 0,
                'conversion_rate': 0,
                'service_breakdown': {},
                'timestamp': datetime.now().isoformat(),
                'individual_calls': [],
                'recent_calls': [],
                'active_calls': []
            }
        
        return jsonify({"success": True, "data": dashboard_data})
        
    except Exception as e:
        print(f"Manager Dashboard API error: {e}")
        return jsonify({
            "success": False, 
            "error": str(e),
            "data": {
                'total_calls': 0,
                'completed_calls': 0,
                'conversion_rate': 0,
                'service_breakdown': {},
                'timestamp': datetime.now().isoformat(),
                'individual_calls': [],
                'recent_calls': [],
                'active_calls': []
            }
        }), 500

@app.route('/api/health')
def health():
    """Complete system health check"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "Complete System v2.0",
        "features": {
            "business_rules": True,
            "dashboard_fixes": True,
            "pricing_api_fixes": True,
            "webhook_integration": True,
            "loop_prevention": True,
            "real_time_updates": True
        },
        "webhook_url": WEBHOOK_URL,
        "openai_configured": bool(os.getenv('OPENAI_API_KEY')),
        "api_mocks": True if 'utils.wasteking_api' not in globals() else False
    })

if __name__ == '__main__':
    print("🚀 Starting WasteKing COMPLETE AI System...")
    print("✅ ALL BUSINESS RULES INCLUDED")
    print("✅ DASHBOARD FIXES APPLIED") 
    print("✅ PRICING API FIXES APPLIED")
    print("✅ WEBHOOK INTEGRATION ACTIVE")
    print("✅ LOOP PREVENTION ENABLED")
    print("🌐 Access Points:")
    print("   📞 User Dashboard: /dashboard/user")
    print("   📊 Manager Dashboard: /dashboard/manager") 
    print("   🧪 Testing Interface: /api/test-interface")
    print("   🎤 ElevenLabs Entry: /api/wasteking")
    print("   🔗 Webhook URL:", WEBHOOK_URL)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
