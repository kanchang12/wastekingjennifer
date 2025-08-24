import re
import json
import os
import requests
from datetime import datetime
from utils.wasteking_api import complete_booking, create_booking, get_pricing


class BaseAgent:
    def __init__(self, rules_processor):
        self.rules_processor = rules_processor
        self.service_type = getattr(self, 'service_type', 'base')
        self._rules_cache = {}  # Cache for frequently accessed rules
        self.conversations = {}  # Store conversation state
        
        # Cache common PDF rules on initialization
        self._cache_common_rules()
        
    def _cache_common_rules(self):
        """Cache frequently used rules from PDF for faster access"""
        try:
            pdf_rules = self.rules_processor.rules_data
            
            # Cache LOCK rules (most frequently checked)
            self._rules_cache['lock_rules'] = pdf_rules.get('lock_rules', {})
            
            # Cache exact scripts for this agent type
            all_exact_scripts = pdf_rules.get('exact_scripts', {})
            if self.service_type == 'skip':
                self._rules_cache['exact_scripts'] = {k: v for k, v in all_exact_scripts.items() 
                                                    if k in ['sofa_prohibited', 'heavy_materials', 'mav_suggestion', 'permit_script']}
            elif self.service_type == 'mav':
                self._rules_cache['exact_scripts'] = {k: v for k, v in all_exact_scripts.items()
                                                    if k in ['time_restriction', 'sunday_collection']}
            elif self.service_type == 'grab':
                self._rules_cache['exact_scripts'] = {k: v for k, v in all_exact_scripts.items()
                                                    if k in ['grab_6_wheeler', 'grab_8_wheeler']}
            
            # Cache transfer rules
            self._rules_cache['transfer_rules'] = pdf_rules.get('transfer_rules', {})
            
            # Cache office hours
            self._rules_cache['office_hours'] = pdf_rules.get('office_hours', {})
            
            # Cache prohibited items for this agent
            self._rules_cache['prohibited_items'] = pdf_rules.get('prohibited_items', {})
            
            print(f"✅ Cached rules for {self.service_type} agent")
            
        except Exception as e:
            print(f"❌ Error caching rules: {e}")
            # Fallback to empty cache
            self._rules_cache = {'lock_rules': {}, 'exact_scripts': {}, 'transfer_rules': {}}

    def get_cached_rule(self, category, rule_name=None):
        """Get rule from cache (fast) or PDF (slower fallback)"""
        try:
            if category in self._rules_cache:
                if rule_name:
                    return self._rules_cache[category].get(rule_name)
                return self._rules_cache[category]
            
            # Fallback to PDF if not cached
            pdf_rules = self.rules_processor.rules_data
            category_rules = pdf_rules.get(category, {})
            
            if rule_name:
                return category_rules.get(rule_name)
            return category_rules
            
        except Exception as e:
            print(f"❌ Error getting rule {category}.{rule_name}: {e}")
            return None

    def extract_data(self, message):
        """Extract customer data from message"""
        data = {}
        message_lower = message.lower()

        # Extract postcode
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
        if postcode_match:
            data['postcode'] = postcode_match.group(1).replace(' ', '')
            print(f"✅ Extracted postcode: {data['postcode']}")

        # Extract phone
        phone_match = re.search(r'\b(\d{10,11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ Extracted phone: {data['phone']}")

        # Extract name
        if 'kanchen' in message_lower:
            data['firstName'] = 'Kanchen'
            print(f"✅ Extracted name: Kanchen")
        else:
            name_patterns = [
                r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
                r'^([A-Z][a-z]+)\s+(?:wants|needs)',
                r'^([A-Z][a-z]+),',
                r'for\s+([A-Z][a-z]+),',
            ]
            for pattern in name_patterns:
                name_match = re.search(pattern, message)
                if name_match:
                    data['firstName'] = name_match.group(1).strip().title()
                    print(f"✅ Extracted name: {data['firstName']}")
                    break
        return data

    def should_book(self, message):
        """Check if user wants to proceed with booking"""
        message_lower = message.lower()
        
        # Direct booking requests
        booking_phrases = [
            'payment link', 'pay link', 'booking', 'book it', 'book this',
            'send payment', 'complete booking', 'finish booking', 'proceed with booking',
            'confirm booking', 'make booking', 'create booking', 'place order',
            'send me the link', 'i want to book', 'ready to book', 'lets book',
            'checkout', 'complete order', 'finalize booking', 'secure booking',
            'reserve this', 'confirm this', 'i\'ll take it', 'that works',
            'perfect', 'sounds good', 'thats fine', 'arrange this'
        ]
        
        # Positive responses
        positive_words = ['yes', 'yeah', 'yep', 'ok', 'okay', 'alright', 'sure', 'lets do it', 'go ahead', 'proceed']
        
        # Check for explicit booking requests
        if any(phrase in message_lower for phrase in booking_phrases):
            return True
            
        # Check for positive responses
        return any(word in message_lower for word in positive_words)

    def should_get_price(self, message):
        """Check if user wants pricing"""
        price_words = ['price', 'cost', 'quote', 'how much', 'availability', 'pricing']
        return any(word in message.lower() for word in price_words)

    def check_office_hours_and_transfer(self, price=None):
        """Check office hours and transfer rules"""
        return self.rules_processor.check_office_hours_and_transfer_rules(
            message="", agent_type=self.service_type, price=price
        )

    def needs_transfer(self, price):
        """Check transfer rules using rules processor"""
        transfer_check = self.check_office_hours_and_transfer(price)
        
        if transfer_check.get('situation') == 'OUT_OF_OFFICE_HOURS':
            lock_rule = self.get_cached_rule('lock_rules', 'LOCK_9_OUT_HOURS_CALLBACK')
            print(f"🌙 {lock_rule or 'OUT OF HOURS - MAKE THE SALE'}")
            return False
            
        elif transfer_check.get('situation') == 'OFFICE_HOURS':
            if transfer_check.get('transfer_allowed'):
                print(f"🏢 TRANSFER NEEDED: {transfer_check.get('reason')}")
                return True
            else:
                print(f"🏢 NO TRANSFER: {transfer_check.get('reason')}")
                return False
                
        return False

    def enforce_lock_rules(self, message, state):
        """Enforce PDF LOCK rules with caching"""
        # Get cached LOCK rules
        lock_rules = self.get_cached_rule('lock_rules')
        
        # LOCK_4 & LOCK_8: Don't re-ask for stored information
        required_fields = ['firstName', 'postcode', 'phone', 'service']
        missing_fields = [field for field in required_fields if not state.get(field)]
        
        if len(missing_fields) > 1:
            # LOCK_3: One question at a time
            return missing_fields[0]
        elif len(missing_fields) == 1:
            return missing_fields[0]
        
        return None

    def get_exact_script(self, script_name):
        """Get exact script from cached PDF rules"""
        exact_scripts = self.get_cached_rule('exact_scripts')
        return exact_scripts.get(script_name, "") if exact_scripts else ""

    def validate_response_compliance(self, response):
        """Validate response against business rules"""
        validation = self.rules_processor.validate_response_against_rules(response, self.service_type)
        
        if not validation.get('compliant'):
            print(f"🚨 RULE VIOLATIONS: {validation.get('violations')}")
        
        return validation

    def validate_pdf_compliance(self, response):
        """Validate against PDF rules using cache"""
        violations = []
        
        # Check LOCK rules from PDF
        lock_rules = self.get_cached_rule('lock_rules')
        
        # LOCK_1: No greetings (from PDF)
        if 'thomas' in response.lower() or any(greeting in response.lower() for greeting in ['hi i am', 'hello']):
            violations.append(f"PDF LOCK_1: {lock_rules.get('LOCK_1_NO_GREETING', 'No greeting allowed')}")
        
        # LOCK_3: One question at a time (from PDF)
        if response.count('?') > 1:
            violations.append(f"PDF LOCK_3: {lock_rules.get('LOCK_3_ONE_QUESTION', 'One question only')}")
        
        # Check hardcoded price violations (legal compliance from PDF)
        pricing_check = self.rules_processor.validate_no_hardcoded_prices(response)
        if not pricing_check.get('legal_compliant'):
            violations.extend(pricing_check.get('violations', []))
        
        if violations:
            print(f"🚨 PDF RULE VIOLATIONS: {violations}")
        
        return len(violations) == 0

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and ask user to confirm"""
        try:
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            service_type = state.get('type', self._get_default_type())
            
            # Get pricing
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], service_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', service_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check transfer rules
                if self.needs_transfer(price_num):
                    return f"For this £{price_num} booking, I need to transfer you to our specialist team who can help you complete this."
                
                response = f"💰 {state['type']} {state['service']} at {state['postcode']}: {state['price']} excluding V-A-T. Would you like to book this?"
                
                # Validate response against rules
                self.validate_response_compliance(response)
                return response
            else:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """Get pricing and complete booking immediately"""
        try:
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            service_type = state.get('type', self._get_default_type())
            
            # Get pricing
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], service_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', service_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check transfer rules
                if self.needs_transfer(price_num):
                    return f"For this £{price_num} booking, I need to transfer you to our specialist team who can help you complete this."
                
                print("🚀 GOT PRICING - NOW COMPLETING BOOKING IMMEDIATELY")
                # Complete booking immediately
                return self.complete_booking_proper(state)
            else:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def complete_booking_proper(self, state):
        """Complete booking with payment link + RULES COMPLIANCE"""
        try:
            print("🚀 COMPLETING BOOKING...")
            
            # Prepare customer data
            customer_data = {
                'firstName': state.get('firstName'),
                'phone': state.get('phone'),
                'postcode': state.get('postcode'),
                'service': state.get('service'),
                'type': state.get('type')
            }
            
            print(f"📋 CUSTOMER DATA: {customer_data}")
            
            # Call the complete booking API (NO HARDCODED PRICES)
            result = complete_booking(customer_data)
            
            if result.get('success'):
                booking_ref = result['booking_ref']
                price = result['price']
                payment_link = result.get('payment_link')
                
                print(f"✅ BOOKING SUCCESS: {booking_ref}, {price}")
                
                # Update state
                state['booking_completed'] = True
                state['booking_ref'] = booking_ref
                state['final_price'] = price
                
                # Send SMS if phone provided
                if payment_link and state.get('phone'):
                    self.send_sms(state['firstName'], state['phone'], booking_ref, price, payment_link)
                
                # Build response with V-A-T spelling rule
                response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: {price} excluding V-A-T"
                if payment_link:
                    response += f"\n💳 Payment link sent to your phone: {payment_link}"
                
                # Use exact final ending script
                final_script = self.get_exact_script('final_ending')
                if final_script:
                    response += f"\n{final_script}"
                
                return response
            else:
                print(f"❌ BOOKING FAILED: {result}")
                return "Unable to complete booking. Our team will call you back."
                
        except Exception as e:
            print(f"❌ BOOKING ERROR: {e}")
            return "Booking issue occurred. Our team will contact you."

    def send_sms(self, name, phone, booking_ref, price, payment_link):
        """Send SMS with payment link"""
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

    def process_message(self, message, conversation_id="default"):
        """Main message processing method"""
        state = self.conversations.get(conversation_id, {})
        print(f"📂 LOADED STATE: {state}")

        new_data = self.extract_data(message)
        print(f"🔍 NEW DATA: {new_data}")

        state.update(new_data)
        print(f"🔄 MERGED STATE: {state}")

        self.conversations[conversation_id] = state

        response = self.get_next_response(message, state, conversation_id)
        return response

    def get_next_response(self, message, state, conversation_id):
        """Override in child classes"""
        return "How can I help you?"

    def _get_default_type(self):
        """Override in child classes to provide default service type"""
        return "default"


class SkipAgent(BaseAgent):
    def __init__(self, rules_processor):
        self.service_type = 'skip'
        super().__init__(rules_processor)

    def _get_default_type(self):
        return '8yd'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['skip', 'skip hire']):
            data['service'] = 'skip'
            
            # Check for heavy materials - LOCK_7 + skip rules
            if any(material in message_lower for material in ['soil', 'rubble', 'concrete', 'heavy']):
                data['heavy_materials'] = True
                data['type'] = '8yd'  # Heavy materials MAX 8-yard
            elif any(size in message_lower for size in ['8-yard', '8 yard', '8yd']):
                data['type'] = '8yd'
            elif any(size in message_lower for size in ['6-yard', '6 yard', '6yd']):
                data['type'] = '6yd'
            elif any(size in message_lower for size in ['4-yard', '4 yard', '4yd']):
                data['type'] = '4yd'
            elif any(size in message_lower for size in ['12-yard', '12 yard', '12yd']):
                data['type'] = '12yd'
            else:
                data['type'] = '8yd'  # Default
        
        # Check for prohibited items
        if any(item in message_lower for item in ['sofa', 'upholstered', 'furniture']):
            data['prohibited_item'] = 'sofa'
                
        return data

    def get_next_response(self, message, state, conversation_id):
        """RULES-COMPLIANT LOGIC"""
        # LOCK_11: Answer customer questions FIRST
        if any(prohibited in message.lower() for prohibited in ['sofa', 'upholstered']):
            # Use exact script for prohibited items
            return self.get_exact_script('sofa_prohibited')
        
        # Check if user wants to book
        wants_to_book = self.should_book(message)
        
        # LOCK_4 + LOCK_8: Don't re-ask for stored information
        missing_field = self.enforce_lock_rules(message, state)
        
        if missing_field == 'firstName':
            return "What's your name?"
        elif missing_field == 'postcode':
            return "What's your postcode?"  
        elif missing_field == 'phone':
            return "What's your phone number?"
        elif missing_field == 'service':
            return "What service do you need?"
        
        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            response = self.complete_booking_proper(state)
            # Validate response compliance
            self.validate_response_compliance(response)
            return response
        
        # If user wants to book but no price yet, get price and book
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            response = self.get_pricing_and_complete_booking(state, conversation_id)
            self.validate_response_compliance(response)
            return response
        
        # Check for heavy materials rule
        if state.get('heavy_materials'):
            response = self.get_exact_script('heavy_materials')
            if not response:
                response = "For heavy materials such as soil & rubble, the largest skip you can have is 8-yard. Shall I get you the cost of an 8-yard skip?"
            return response
        
        # If we have all data but no price yet, get pricing
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        # If we have pricing, ask to book
        elif state.get('price'):
            # Check for MAV suggestion if 8-yard + light materials
            if state.get('type') == '8yd' and not state.get('heavy_materials'):
                mav_script = self.get_exact_script('mav_suggestion')
                if mav_script:
                    return mav_script
            
            return f"💰 {state['type']} skip hire at {state['postcode']}: {state['price']}. Would you like to book this?"
        
        return "How can I help you with skip hire?"


class MAVAgent(BaseAgent):
    def __init__(self, rules_processor):
        self.service_type = 'mav'
        super().__init__(rules_processor)

    def _get_default_type(self):
        return 'small'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['man and van', 'mav', 'man & van']):
            data['service'] = 'mav'
            
            # Hardcoded common size detection
            if any(size in message_lower for size in ['large']):
                data['type'] = 'large'
            elif any(size in message_lower for size in ['medium']):
                data['type'] = 'medium'
            elif any(size in message_lower for size in ['small']):
                data['type'] = 'small'
            else:
                data['type'] = 'small'  # Default
            
            # PDF rule-based transfer triggers
            if any(material in message_lower for material in ['soil', 'rubble', 'concrete', 'heavy']):
                data['heavy_materials'] = True
            if any(access in message_lower for access in ['stairs', 'flat', 'apartment', 'floor']):
                data['difficult_access'] = True
                
        return data

    def get_next_response(self, message, state, conversation_id):
        """HARDCODED logic + PDF transfer rules"""
        # PDF rules: Immediate transfer requirements during office hours
        transfer_check = self.check_office_hours_and_transfer()
        
        if state.get('heavy_materials') and transfer_check.get('is_office_hours'):
            return "Heavy materials require our specialist team. Let me transfer you to them now."
        elif state.get('difficult_access') and transfer_check.get('is_office_hours'):
            return "For stairs and difficult access, our specialist team can help you better. Let me transfer you."
        
        # Hardcoded booking flow
        wants_to_book = self.should_book(message)
        
        # PDF LOCK rules for missing data
        missing_field = self.enforce_lock_rules(message, state)
        
        if missing_field == 'firstName':
            return "What's your name?"
        elif missing_field == 'postcode':
            return "What's your postcode?"
        elif missing_field == 'phone':
            return "What's your phone number?"
        elif missing_field == 'service':
            return "What service do you need?"
        
        # Hardcoded booking completion
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            response = self.complete_booking_proper(state)
            self.validate_pdf_compliance(response)
            return response
        
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            response = self.get_pricing_and_complete_booking(state, conversation_id)
            self.validate_pdf_compliance(response)
            return response
        
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        elif state.get('price'):
            return f"💰 {state['type']} man & van at {state['postcode']}: {state['price']}. Would you like to book this?"
        
        return "How can I help you with man & van service?"


class GrabAgent(BaseAgent):
    def __init__(self, rules_processor):
        self.service_type = 'grab'
        super().__init__(rules_processor)

    def _get_default_type(self):
        return '6t'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['grab', 'grab hire']):
            data['service'] = 'grab'
            
            # Hardcoded common size detection with PDF terminology
            if any(size in message_lower for size in ['8-wheeler', '8 wheel', '16-tonne', '8-tonne']):
                data['type'] = '8t'
                data['script_used'] = 'grab_8_wheeler'
            elif any(size in message_lower for size in ['6-wheeler', '6 wheel', '12-tonne', '6-tonne']):
                data['type'] = '6t'
                data['script_used'] = 'grab_6_wheeler'
            else:
                data['type'] = '6t'  # Default
        else:
            # DEFAULT MANAGER - handles everything else (hardcoded)
            data['service'] = 'grab'
            data['type'] = '6t'
            
        # PDF rule-based immediate transfer triggers
        if any(mixed in message_lower for mixed in ['mixed materials', 'various', 'different types']):
            data['mixed_materials'] = True
        
        if any(wait in message_lower for wait in ['wait and load', 'wait & load', 'wait load']):
            data['wait_and_load'] = True
                
        return data

    def get_next_response(self, message, state, conversation_id):
        """HARDCODED logic + PDF immediate transfer rules"""
        # PDF rules: IMMEDIATE TRANSFERS (during office hours)
        transfer_check = self.check_office_hours_and_transfer()
        
        if state.get('mixed_materials') and transfer_check.get('is_office_hours'):
            return "Mixed materials require our specialist team. Let me transfer you immediately."
        elif state.get('wait_and_load'):
            return "Wait & load skip service requires immediate transfer to our specialist team."
        
        # PDF exact scripts for terminology
        if state.get('script_used') == 'grab_8_wheeler':
            script = self.get_exact_script('grab_8_wheeler')
            if script:
                return script
        elif state.get('script_used') == 'grab_6_wheeler':
            script = self.get_exact_script('grab_6_wheeler')  
            if script:
                return script
        
        # Hardcoded booking flow
        wants_to_book = self.should_book(message)
        
        # PDF LOCK rules for missing data
        missing_field = self.enforce_lock_rules(message, state)
        
        if missing_field == 'firstName':
            return "What's your name?"
        elif missing_field == 'postcode':
            return "What's your postcode?"
        elif missing_field == 'phone':
            return "What's your phone number?"
        elif missing_field == 'service':
            return "What service do you need?"
        
        # Hardcoded booking completion
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            response = self.complete_booking_proper(state)
            self.validate_pdf_compliance(response)
            return response
        
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            response = self.get_pricing_and_complete_booking(state, conversation_id)
            self.validate_pdf_compliance(response)
            return response
        
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        elif state.get('price'):
            return f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']}. Would you like to book this?"
        
        return "How can I help you with grab hire?"
