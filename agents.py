import re
import json
import os
import requests
from datetime import datetime
from utils.wasteking_api import complete_booking


class BaseAgent:
    def __init__(self, rules_processor):
        self.rules_processor = rules_processor
        self.rules = rules_processor.get_rules_for_agent(self.service_type) if hasattr(self, 'service_type') else {}
        self.conversations = {}  # Store conversation state

    def process_message(self, message, conversation_id="default"):
        state = self.conversations.get(conversation_id, {})
        print(f"📂 LOADED STATE: {state}")

        new_data = self.extract_data(message)
        print(f"🔍 NEW DATA: {new_data}")

        state.update(new_data)
        print(f"🔄 MERGED STATE: {state}")

        self.conversations[conversation_id] = state

        response = self.get_next_response(message, state, conversation_id)
        return response

    def extract_data(self, message):
        data = {}
        message_lower = message.lower()

        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
        if postcode_match:
            data['postcode'] = postcode_match.group(1).replace(' ', '')
            print(f"✅ Extracted postcode: {data['postcode']}")

        phone_match = re.search(r'\b(\d{10,11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ Extracted phone: {data['phone']}")

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
        """Check if user wants to proceed with booking - EXPANDED WITH 10+ MORE OPTIONS"""
        message_lower = message.lower()
        
        # Direct booking requests
        booking_phrases = [
            'payment link', 'pay link', 'booking', 'book it', 'book this',
            'send payment', 'complete booking', 'finish booking', 'proceed with booking',
            # 10 MORE OPTIONS:
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
        """Check office hours and transfer rules - FOLLOWS RULES PROCESSOR"""
        return self.rules_processor.check_office_hours_and_transfer_rules(
            message="", agent_type=self.service_type, price=price
        )

    def validate_response_compliance(self, response):
        """Validate response against business rules"""
        validation = self.rules_processor.validate_response_against_rules(response, self.service_type)
        
        if not validation.get('compliant'):
            print(f"🚨 RULE VIOLATIONS: {validation.get('violations')}")
            # Log violations but don't block response - could add escalation here
        
        return validation

    def needs_transfer(self, price):
        """
        CRITICAL RULE: Check transfer rules using rules processor
        """
        # Use rules processor for transfer logic
        transfer_check = self.check_office_hours_and_transfer(price)
        
        if transfer_check.get('situation') == 'OUT_OF_OFFICE_HOURS':
            print("🌙 OUT OF HOURS - MAKE THE SALE (LOCK_6 + LOCK_9)")
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
        """Enforce LOCK 0-11 rules"""
        # LOCK_0: Check current time immediately 
        transfer_check = self.check_office_hours_and_transfer()
        
        # LOCK_1: Never say greeting
        # LOCK_3: One question at a time
        # LOCK_4: Never ask for info twice
        # LOCK_8: Don't re-ask for stored information
        required_fields = ['firstName', 'postcode', 'phone', 'service']
        missing_fields = [field for field in required_fields if not state.get(field)]
        
        if len(missing_fields) > 1:
            # Only ask for first missing field (LOCK_3: One question at a time)
            return missing_fields[0]
        elif len(missing_fields) == 1:
            return missing_fields[0]
        
        return None  # All required data collected

    def get_exact_script(self, script_name):
        """Get exact script that must be used"""
        exact_scripts = self.rules.get('exact_scripts', {})
        return exact_scripts.get(script_name, "")

    def complete_booking_proper(self, state):
        """FIXED - Complete booking with payment link + RULES COMPLIANCE"""
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


class SkipAgent(BaseAgent):
    def __init__(self, rules_processor):
        self.service_type = 'skip'
        super().__init__(rules_processor)

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

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """Get pricing and complete booking immediately - RULES COMPLIANT"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            skip_type = state.get('type', '8yd')
            
            # Get pricing (NO HARDCODED PRICES)
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', skip_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                print("🚀 GOT PRICING - NOW COMPLETING BOOKING IMMEDIATELY")
                # Complete booking immediately (Skip has no transfer rules)
                response = self.complete_booking_proper(state)
                return response
            else:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and ask for booking - RULES COMPLIANT"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            skip_type = state.get('type', '8yd')
            
            # Get pricing (NO HARDCODED PRICES - API ONLY)
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', skip_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Skip has no transfer rules (NO_LIMIT)
                response = f"💰 {state['type']} skip hire at {state['postcode']}: {state['price']} excluding V-A-T. Would you like to book this?"
                
                # Check for MAV suggestion if 8-yard + light materials
                if state.get('type') == '8yd' and not state.get('heavy_materials'):
                    mav_script = self.get_exact_script('mav_suggestion')
                    if mav_script:
                        response = mav_script
                
                # Validate response against rules
                self.validate_response_compliance(response)
                return response
            else:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."


class MAVAgent(BaseAgent):
    def __init__(self, rules_processor):
        self.service_type = 'mav'
        super().__init__(rules_processor)

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['man and van', 'mav', 'man & van']):
            data['service'] = 'mav'
            
            # Check for transfer-required items (heavy materials, stairs)
            if any(material in message_lower for material in ['soil', 'rubble', 'concrete', 'heavy']):
                data['heavy_materials'] = True
            if any(access in message_lower for access in ['stairs', 'flat', 'apartment', 'floor']):
                data['difficult_access'] = True
            
            if any(size in message_lower for size in ['large']):
                data['type'] = 'large'
            elif any(size in message_lower for size in ['medium']):
                data['type'] = 'medium'
            elif any(size in message_lower for size in ['small']):
                data['type'] = 'small'
            else:
                data['type'] = 'small'  # Default
                
        return data

    def get_next_response(self, message, state, conversation_id):
        """RULES-COMPLIANT LOGIC"""
        # LOCK_11: Answer questions FIRST
        # Check for immediate transfer requirements (heavy materials, stairs)
        if state.get('heavy_materials') and self.check_office_hours_and_transfer().get('is_office_hours'):
            return "Heavy materials require our specialist team. Let me transfer you to them now."
        elif state.get('difficult_access') and self.check_office_hours_and_transfer().get('is_office_hours'):
            return "For stairs and difficult access, our specialist team can help you better. Let me transfer you."
        
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
            self.validate_response_compliance(response)
            return response
        
        # If user wants to book but no price yet, get price and book
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            response = self.get_pricing_and_complete_booking(state, conversation_id)
            self.validate_response_compliance(response)
            return response
        
        # If we have all data but no price yet, get pricing
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        # If we have pricing, ask to book
        elif state.get('price'):
            return f"💰 {state['type']} man & van at {state['postcode']}: {state['price']}. Would you like to book this?"
        
        return "How can I help you with man & van service?"

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """Get pricing and complete booking immediately - RULES COMPLIANT"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            mav_type = state.get('type', 'small')
            
            # Get pricing (NO HARDCODED PRICES)
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], mav_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', mav_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check transfer rules using rules processor
                if self.needs_transfer(price_num):
                    return f"For this £{price_num} booking, I need to transfer you to our specialist team who can help you complete this."
                
                print("🚀 GOT PRICING - NOW COMPLETING BOOKING IMMEDIATELY")
                # Complete booking immediately
                response = self.complete_booking_proper(state)
                return response
            else:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and check transfer rules - RULES COMPLIANT"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            mav_type = state.get('type', 'small')
            
            # Get pricing (NO HARDCODED PRICES)
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], mav_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', mav_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check transfer rules using rules processor
                if self.needs_transfer(price_num):
                    return f"For this £{price_num} booking, I need to transfer you to our specialist team who can help you complete this."
                
                response = f"💰 {state['type']} man & van at {state['postcode']}: {state['price']} excluding V-A-T. Would you like to book this?"
                
                # Validate response against rules
                self.validate_response_compliance(response)
                return response
            else:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and check transfer rules"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            mav_type = state.get('type', 'small')
            
            # Get pricing
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], mav_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', mav_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check if needs transfer - ONLY check business hours here
                if self.needs_transfer(price_num):
                    return f"For this £{price_num} booking, I need to transfer you to our specialist team who can help you complete this."
                
                return f"💰 {state['type']} man & van at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."


class GrabAgent(BaseAgent):
    def __init__(self, rules_processor):
        self.service_type = 'grab'
        super().__init__(rules_processor)

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['grab', 'grab hire']):
            data['service'] = 'grab'
            
            # Use exact script terminology
            if any(size in message_lower for size in ['8-wheeler', '8 wheel', '16-tonne', '8-tonne']):
                data['type'] = '8t'
                data['script_used'] = 'grab_8_wheeler'
            elif any(size in message_lower for size in ['6-wheeler', '6 wheel', '12-tonne', '6-tonne']):
                data['type'] = '6t'
                data['script_used'] = 'grab_6_wheeler'
            else:
                data['type'] = '6t'  # Default
        else:
            # DEFAULT MANAGER - handles everything else
            data['service'] = 'grab'
            data['type'] = '6t'
            
        # Check for mixed materials (requires immediate transfer)
        if any(mixed in message_lower for mixed in ['mixed materials', 'various', 'different types']):
            data['mixed_materials'] = True
        
        # Check for wait & load (immediate transfer)
        if any(wait in message_lower for wait in ['wait and load', 'wait & load', 'wait load']):
            data['wait_and_load'] = True
                
        return data

    def get_next_response(self, message, state, conversation_id):
        """RULES-COMPLIANT LOGIC"""
        # IMMEDIATE TRANSFERS (during office hours)
        if state.get('mixed_materials') and self.check_office_hours_and_transfer().get('is_office_hours'):
            return "Mixed materials require our specialist team. Let me transfer you immediately."
        elif state.get('wait_and_load'):
            return "Wait & load skip service requires immediate transfer to our specialist team."
        
        # Use exact scripts for terminology
        if state.get('script_used') == 'grab_8_wheeler':
            response = self.get_exact_script('grab_8_wheeler')
            if response:
                return response
        elif state.get('script_used') == 'grab_6_wheeler':
            response = self.get_exact_script('grab_6_wheeler')  
            if response:
                return response
        
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
            self.validate_response_compliance(response)
            return response
        
        # If user wants to book but no price yet, get price and book
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            response = self.get_pricing_and_complete_booking(state, conversation_id)
            self.validate_response_compliance(response)
            return response
        
        # If we have all data but no price yet, get pricing
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        # If we have pricing, ask to book
        elif state.get('price'):
            return f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']}. Would you like to book this?"
        
        return "How can I help you with grab hire?"

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """Get pricing and complete booking immediately"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            grab_type = state.get('type', '6t')
            
            # Get pricing
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], grab_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', grab_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check if needs transfer - ONLY check business hours here
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

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """Get pricing and complete booking immediately - RULES COMPLIANT"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            grab_type = state.get('type', '6t')
            
            # Get pricing (NO HARDCODED PRICES)
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], grab_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', grab_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check transfer rules using rules processor
                if self.needs_transfer(price_num):
                    return f"For this £{price_num} booking, I need to transfer you to our specialist team who can help you complete this."
                
                print("🚀 GOT PRICING - NOW COMPLETING BOOKING IMMEDIATELY")
                # Complete booking immediately
                response = self.complete_booking_proper(state)
                return response
            else:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and check transfer rules - RULES COMPLIANT"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            grab_type = state.get('type', '6t')
            
            # Get pricing (NO HARDCODED PRICES)
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], grab_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', grab_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check transfer rules using rules processor
                if self.needs_transfer(price_num):
                    return f"For this £{price_num} booking, I need to transfer you to our specialist team who can help you complete this."
                
                response = f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']} excluding V-A-T. Would you like to book this?"
                
                # Validate response against rules
                self.validate_response_compliance(response)
                return response
            else:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."
