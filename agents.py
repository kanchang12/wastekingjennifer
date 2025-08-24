import re
import json
import os
import requests
from datetime import datetime
from utils.wasteking_api import complete_booking


class BaseAgent:
    def __init__(self, rules_processor):
        self.rules = rules_processor
        self.conversations = {}  # Store conversation state
        
        # Configurable rules list - can be updated without code changes
        self.rules_list = [
            # "I will write new rules",
            # "now it will be blank",
            # "then what ever will come I will add",
            # "so that I dont need to change the code again"
        ]

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
        """MOST IMPORTANT: Check if user wants to proceed with booking"""
        message_lower = message.lower()
        
        # Direct booking requests
        booking_phrases = [
            'payment link', 'pay link', 'booking', 'book it', 'book this',
            'send payment', 'complete booking', 'finish booking', 'proceed with booking',
            'confirm booking', 'make booking', 'create booking', 'place order',
            'send me the link', 'i want to book', 'ready to book', 'lets book',
            'checkout', 'complete order', 'finalize booking', 'secure booking',
            'reserve this', 'confirm this', 'i\'ll take it', 'that works',
            'perfect', 'sounds good', 'thats fine', 'arrange this', 'lets go'
        ]
        
        # Positive responses
        positive_words = ['yes', 'yeah', 'yep', 'ok', 'okay', 'alright', 'sure', 'lets do it', 'go ahead', 'proceed']
        
        # Check for explicit booking requests
        if any(phrase in message_lower for phrase in booking_phrases):
            return True
            
        # Check for positive responses
        return any(word in message_lower for word in positive_words)

    def is_business_hours(self):
        """Business hours from PDF - EXACT"""
        now = datetime.now()
        day_of_week = now.weekday()  # 0=Monday, 6=Sunday
        hour = now.hour
        
        if day_of_week < 4:  # Monday-Thursday: 8:00am-5:00pm
            return 8 <= hour < 17
        elif day_of_week == 4:  # Friday: 8:00am-4:30pm
            return 8 <= hour < 16 or (hour == 16 and datetime.now().minute < 30)
        elif day_of_week == 5:  # Saturday: 9:00am-12:00pm
            return 9 <= hour < 12
        return False  # Sunday closed

    def forward_rule(self, reason, conversation_id="default"):
        """FORWARD RULE: Transfer or SMS based on business hours"""
        if self.is_business_hours():
            # Within office hours: transfer (number will be added to 11 labs)
            return f"Let me put you through to our specialist team for {reason}."
        else:
            # Outside office hours: take details and send SMS
            state = self.conversations.get(conversation_id, {})
            self.send_forward_sms(conversation_id, state.get('firstName', 'Customer'), reason)
            return f"Our office is currently closed. I can take your details and have our specialist team call you back first thing tomorrow for {reason}."

    def send_forward_sms(self, conversation_id, customer_name, description):
        """Send forward SMS with eleven labs conversation ID"""
        try:
            twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
            twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
            twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
            forward_number = "+447823656762"
            
            if twilio_sid and twilio_token and twilio_phone:
                from twilio.rest import Client
                client = Client(twilio_sid, twilio_token)
                
                message = f"Eleven Labs conversation ID: {conversation_id}\nCustomer name: {customer_name}\nShort description: {description}"
                
                client.messages.create(body=message, from_=twilio_phone, to=forward_number)
                print(f"✅ Forward SMS sent: {message}")
        except Exception as e:
            print(f"❌ Forward SMS error: {e}")

    def check_specialist_service(self, message):
        """Check if request is for specialist services that need forwarding"""
        message_lower = message.lower()
        
        specialist_services = [
            'hazardous waste', 'asbestos', 'weee', 'electrical waste', 'chemical disposal',
            'medical waste', 'trade waste', 'wheelie bins', 'portable toilet', 'welfare unit',
            'aggregates', 'roro', 'recycling pods', 'road sweeper'
        ]
        
        for service in specialist_services:
            if service in message_lower:
                return service
        return None

    def complete_booking_proper(self, state):
        """MOST IMPORTANT: Complete booking with payment link"""
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
            
            # Call the complete booking API
            result = complete_booking(customer_data)
            
            if result.get('success'):
                booking_ref = result['booking_ref']
                price = result['price']
                payment_link = result.get('payment_link')
                
                print(f"✅ BOOKING SUCCESS: {booking_ref}, {price}")
                
                # Update state with REQUIRED date and time
                current_datetime = datetime.now()
                state['booking_completed'] = True
                state['booking_ref'] = booking_ref
                state['final_price'] = price
                state['booking_date'] = current_datetime.strftime('%Y%m%d')  # 20250824 format
                state['booking_time'] = current_datetime.strftime('%I:%M %p')  # 12:30 PM format
                
                # MOST IMPORTANT: Send SMS with payment link
                if payment_link and state.get('phone'):
                    self.send_sms(state['firstName'], state['phone'], booking_ref, price, payment_link)
                
                # PDF COMPLIANT response
                response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: {price}\n"
                response += "Thank you for choosing Waste King.\n"
                response += "Our driver will call when they're on their way.\n"
                response += "We can't guarantee exact times, but delivery is between 07:00-18:00\n"
                response += "Collection within 72 hours of delivery\n"
                response += "98% recycling rate\n"
                response += "Partnership with The Salvation Army for textile recycling\n"
                response += "Digital waste transfer notes provided\n"
                response += "We have insured and licensed teams\n"
                response += "⚠️ Please ensure access is available - blocked access incurs £79+VAT wasted journey penalty\n"
                response += "Is there anything else I can help you with today?\n"
                response += "Please leave us a review if you're happy with our service\n"
                response += "Thank you for your time, have a great day, bye!"
                
                if payment_link:
                    response += f"\n💳 Payment link sent to your phone"
                
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
        super().__init__(rules_processor)
        self.service_type = 'skip'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['skip', 'skip hire']):
            data['service'] = 'skip'
            
            # Extract skip size
            if any(size in message_lower for size in ['12-yard', '12 yard', '12yd']):
                data['type'] = '12yd'
            elif any(size in message_lower for size in ['8-yard', '8 yard', '8yd']):
                data['type'] = '8yd'
            elif any(size in message_lower for size in ['6-yard', '6 yard', '6yd']):
                data['type'] = '6yd'
            elif any(size in message_lower for size in ['4-yard', '4 yard', '4yd']):
                data['type'] = '4yd'
            else:
                data['type'] = '8yd'  # Default - most popular nationally
                
        return data

    def get_next_response(self, message, state, conversation_id):
        """PDF COMPLIANT Skip Hire Flow A1-A7"""
        
        # Check for specialist services first
        specialist_service = self.check_specialist_service(message)
        if specialist_service:
            return self.forward_rule(specialist_service, conversation_id)
        
        # MOST IMPORTANT: If user wants to book and we have pricing > 0
        wants_to_book = self.should_book(message)
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            try:
                price_num = float(str(state['price']).replace('£', '').replace(',', ''))
                if price_num > 0:
                    return self.complete_booking_proper(state)
            except:
                pass
        
        # A1: INFORMATION GATHERING SEQUENCE
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your postcode?"
        elif not state.get('phone'):
            return "What's your phone number?"
        elif not state.get('service'):
            return "What service do you need?"
        
        # A2: HEAVY MATERIALS CHECK & MAN & VAN SUGGESTION
        if not state.get('materials_checked'):
            # Check for 12-yard with heavy materials
            if state.get('type') == '12yd' and any(mat in message.lower() for mat in ['soil', 'rubble', 'bricks', 'concrete']):
                state['materials_checked'] = True
                self.conversations[conversation_id] = state
                return "For 12 yard skips, we can only take light materials as heavy materials make the skip too heavy to lift. For heavy materials, I'd recommend an 8 yard skip or smaller."
            
            # CRITICAL BUSINESS RULE - Man & Van suggestion
            if (state.get('type') in ['4yd', '6yd', '8yd'] and 
                not any(mat in message.lower() for mat in ['soil', 'rubble', 'bricks', 'concrete', 'tiles', 'hardcore'])):
                state['materials_checked'] = True
                self.conversations[conversation_id] = state
                return "Since you have light materials for an 8-yard skip, our man & van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man & van options so you can compare prices?"
            
            state['materials_checked'] = True
            self.conversations[conversation_id] = state
        
        # A3: SKIP SIZE & LOCATION
        if not state.get('size_confirmed'):
            if not state.get('type'):
                return "What size skip are you thinking of? We have 4, 6, 8, and 12-yard skips. Our 8-yard is most popular nationally."
            state['size_confirmed'] = True
            self.conversations[conversation_id] = state
        
        if not state.get('location_confirmed'):
            if not any(word in ' '.join(state.get('messages', [])).lower() for word in ['driveway', 'road', 'street', 'outside']):
                return "Will the skip go on your driveway or on the road?"
            
            # PERMIT SCRIPT for road placement
            if any(word in ' '.join(state.get('messages', [])).lower() for word in ['road', 'street', 'outside', 'front', 'pavement']):
                state['permit_required'] = True
                state['location_confirmed'] = True
                self.conversations[conversation_id] = state
                return ("For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote. The permit ensures everything is legal and safe.\n"
                       "Are there any parking bays where the skip will go?\n"
                       "Are there yellow lines in that area?\n"
                       "Are there any parking restrictions on that road?")
            
            state['location_confirmed'] = True
            self.conversations[conversation_id] = state
        
        # A4: ACCESS ASSESSMENT
        if not state.get('access_confirmed'):
            if 'complex' in message.lower() or 'difficult' in message.lower() or 'narrow' in message.lower():
                return self.forward_rule("site assessment", conversation_id)
            
            if not any(word in ' '.join(state.get('messages', [])).lower() for word in ['access', 'narrow', 'bridge']):
                return "Is there easy access for our lorry to deliver the skip? Any low bridges, narrow roads, or parking restrictions?"
            
            state['access_confirmed'] = True
            self.conversations[conversation_id] = state
        
        # A5: PROHIBITED ITEMS SCREENING
        if not state.get('items_checked'):
            prohibited_response = self.check_prohibited_items(' '.join(state.get('messages', [])))
            if prohibited_response:
                state['items_checked'] = True
                state['surcharge_message'] = prohibited_response
                self.conversations[conversation_id] = state
                return prohibited_response
            
            state['items_checked'] = True
            self.conversations[conversation_id] = state
        
        # A6: TIMING & QUOTE GENERATION
        if not state.get('timing_confirmed'):
            if not any(word in ' '.join(state.get('messages', [])).lower() for word in ['when', 'today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                return "When do you need this delivered? We can't guarantee exact times, but delivery is between 7am to 6pm"
            
            # Sunday delivery check
            if 'sunday' in ' '.join(state.get('messages', [])).lower():
                return self.forward_rule("Sunday collection arrangements", conversation_id)
            
            state['timing_confirmed'] = True
            self.conversations[conversation_id] = state
        
        # If user wants to book but we don't have price yet
        if wants_to_book and not state.get('price'):
            return self.get_pricing_and_complete_booking(state, conversation_id)
        
        # Get pricing if all info collected but no price
        if not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        # A7: QUOTE PRESENTATION - SKIP HIRE handles ALL amounts
        if state.get('price'):
            try:
                price_num = float(str(state['price']).replace('£', '').replace(',', ''))
                if price_num > 0:
                    return f"💰 {state['type']} skip hire at {state['postcode']}: {state['price']} including V-A-T. Collection within 72 hours standard. Level load requirement for skip collection. Driver calls when en route. 98% recycling rate. We have insured and licensed teams. Digital waste transfer notes provided. Would you like to book this?"
            except:
                pass
        
        return "How can I help you with skip hire?"

    def check_prohibited_items(self, message_text):
        """Check for prohibited items and return appropriate response"""
        message_lower = message_text.lower()
        
        # Items that require surcharge
        surcharge_items = []
        if any(word in message_lower for word in ['fridge', 'freezer']):
            surcharge_items.append('fridge/freezer (£20 extra)')
        if any(word in message_lower for word in ['mattress', 'mattresses']):
            surcharge_items.append('mattress (£15 extra)')
        if any(word in message_lower for word in ['sofa', 'couch', 'upholstered']):
            return "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service. We charge extra due to EA regulations"
        
        # Items that require transfer
        if 'plasterboard' in message_lower:
            return "Plasterboard requires a separate skip."
        if any(word in message_lower for word in ['gas cylinder', 'paint', 'chemical', 'hazardous']):
            return "We can help with hazardous materials."
        if 'asbestos' in message_lower:
            return self.forward_rule("asbestos collection", "default")
        if any(word in message_lower for word in ['tyre', 'tyres']):
            return "Tyres can't be put in skip"
        
        if surcharge_items:
            return f"I note you have {', '.join(surcharge_items)}. This will be included in your quote."
        
        return None

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """MOST IMPORTANT: Get pricing and complete booking immediately"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            skip_type = state.get('type', '8yd')
            
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            try:
                price_num = float(str(price).replace('£', '').replace(',', ''))
                if price_num > 0:
                    state['price'] = price
                    state['type'] = price_result.get('type', skip_type)
                    state['booking_ref'] = booking_ref
                    self.conversations[conversation_id] = state
                    
                    print("🚀 GOT PRICING - NOW COMPLETING BOOKING IMMEDIATELY")
                    return self.complete_booking_proper(state)
                else:
                    return "Unable to get pricing for your area."
            except:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and ask for booking"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            skip_type = state.get('type', '8yd')
            
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            try:
                price_num = float(str(price).replace('£', '').replace(',', ''))
                if price_num > 0:
                    state['price'] = price
                    state['type'] = price_result.get('type', skip_type)
                    state['booking_ref'] = booking_ref
                    self.conversations[conversation_id] = state
                    
                    return f"💰 {state['type']} skip hire at {state['postcode']}: {state['price']} including V-A-T. Collection within 72 hours standard. Level load requirement for skip collection. Driver calls when en route. 98% recycling rate. We have insured and licensed teams. Digital waste transfer notes provided. Would you like to book this?"
                else:
                    return "Unable to get pricing for your area."
            except:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."


class MAVAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'mav'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()

        if any(word in message_lower for word in ['man and van', 'mav', 'man & van']):
            data['service'] = 'mav'

            if 'large' in message_lower:
                data['type'] = '8yd'
            elif 'medium' in message_lower:
                data['type'] = '6yd'
            elif 'small' in message_lower:
                data['type'] = '4yd'
            else:
                data['type'] = '4yd'  # Default

        return data

    def get_next_response(self, message, state, conversation_id):
        """PDF COMPLIANT Man & Van Flow B1-B6"""
        
        # Check for specialist services first
        specialist_service = self.check_specialist_service(message)
        if specialist_service:
            return self.forward_rule(specialist_service, conversation_id)
        
        # MOST IMPORTANT: If user wants to book and we have pricing > 0
        wants_to_book = self.should_book(message)
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            try:
                price_num = float(str(state['price']).replace('£', '').replace(',', ''))
                if price_num > 0:
                    return self.complete_booking_proper(state)
            except:
                pass

        # B1: INFORMATION GATHERING
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your postcode?"
        elif not state.get('phone'):
            return "What's your phone number?"
        elif not state.get('service'):
            return "What service do you need?"

        # B2: HEAVY MATERIALS CHECK
        if not state.get('heavy_materials_checked'):
            if any(mat in message.lower() for mat in ['soil', 'rubble', 'bricks', 'concrete', 'tiles']):
                return self.forward_rule("heavy materials assessment", conversation_id)
            state['heavy_materials_checked'] = True
            self.conversations[conversation_id] = state

        # B3: VOLUME ASSESSMENT & WEIGHT LIMITS
        if not state.get('volume_assessed'):
            if not state.get('type'):
                return ("How much waste do you have approximately?\n"
                       "We charge by the cubic yard at £30 per yard for light waste.\n"
                       "We allow 100 kilos per cubic yard - for example, 5 yards would be 500 kilos\n"
                       "The majority of our collections are done under our generous weight allowances\n"
                       "We allow generous labour time and 95% of all our jobs are done within the time frame\n"
                       "Although if the collection goes over our labour time, there is a £19 charge per 15 minutes\n"
                       "Think in terms of washing machine loads or black bags. National average is 6 yards for man & van service.")
            state['volume_assessed'] = True
            self.conversations[conversation_id] = state

        # B4: ACCESS ASSESSMENT (CRITICAL)
        if not state.get('access_assessed'):
            if any(word in message.lower() for word in ['stairs', 'flat', 'apartment', 'floor']):
                return self.forward_rule("stairs/flat assessment", conversation_id)
            
            if not any(word in ' '.join(state.get('messages', [])).lower() for word in ['access', 'parking', 'driveway']):
                return ("Where is the waste located and how easy is it to access?\n"
                       "Can we park on the driveway or close to the waste?\n"
                       "Are there any stairs involved?\n"
                       "How far is our parking from the waste?\n"
                       "We have insured and licensed teams")
            
            state['access_assessed'] = True
            self.conversations[conversation_id] = state

        # B5: ADDITIONAL ITEMS & TIMING
        if not state.get('items_timing_checked'):
            # Check timing
            if 'sunday' in ' '.join(state.get('messages', [])).lower():
                return self.forward_rule("Sunday collection arrangements", conversation_id)
            
            # Check prohibited items
            prohibited_response = self.check_prohibited_items_mav(' '.join(state.get('messages', [])))
            if prohibited_response:
                state['items_timing_checked'] = True
                self.conversations[conversation_id] = state
                return prohibited_response
            
            state['items_timing_checked'] = True
            self.conversations[conversation_id] = state

        # If user wants to book but we don't have price yet
        if wants_to_book and not state.get('price'):
            return self.get_pricing_and_complete_booking(state, conversation_id)

        # Get pricing if all info collected but no price
        if not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)

        # B6: QUOTE & PRICING DECISION - Present quote
        if state.get('price'):
            try:
                price_num = float(str(state['price']).replace('£', '').replace(',', ''))
                if price_num > 0:
                    return f"💰 {state['type']} man & van at {state['postcode']}: {state['price']} including V-A-T. Would you like to book this?"
            except:
                pass

        return "How can I help you with man & van service?"

    def check_prohibited_items_mav(self, message_text):
        """Check for prohibited items in Man & Van"""
        message_lower = message_text.lower()
        
        # Items with surcharges for Man & Van
        surcharge_items = []
        if any(word in message_lower for word in ['fridge', 'freezer']):
            surcharge_items.append('fridge/freezer (£20 extra)')
        if any(word in message_lower for word in ['mattress', 'mattresses']):
            surcharge_items.append('mattress (£15 extra)')
        if any(word in message_lower for word in ['sofa', 'couch', 'upholstered']):
            surcharge_items.append('upholstered furniture (£15 extra due to EA regulations)')
        
        if surcharge_items:
            return f"I note you have {', '.join(surcharge_items)}. This will be included in your quote."
        
        return None

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """MOST IMPORTANT: Get pricing and complete booking immediately"""
        try:
            from utils.wasteking_api import create_booking, get_pricing

            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."

            booking_ref = booking_result['booking_ref']
            mav_type = state.get('type', '4yd')

            price_result = get_pricing(booking_ref, state['postcode'], state['service'], mav_type)
            if not price_result.get('success'):
                return "Unable to get pricing for your area."

            price = price_result['price']
            try:
                price_num = float(str(price).replace('£', '').replace(',', ''))
                if price_num > 0:
                    state['price'] = price
                    state['type'] = price_result.get('type', mav_type)
                    state['booking_ref'] = booking_ref
                    self.conversations[conversation_id] = state

                    return self.complete_booking_proper(state)
                else:
                    return "Unable to get pricing for your area."
            except:
                return "Unable to get pricing for your area."

        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and ask for booking"""
        try:
            from utils.wasteking_api import create_booking, get_pricing

            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."

            booking_ref = booking_result['booking_ref']
            mav_type = state.get('type', '4yd')

            price_result = get_pricing(booking_ref, state['postcode'], state['service'], mav_type)
            if not price_result.get('success'):
                return "Unable to get pricing for your area."

            price = price_result['price']
            try:
                price_num = float(str(price).replace('£', '').replace(',', ''))
                if price_num > 0:
                    state['price'] = price
                    state['type'] = price_result.get('type', mav_type)
                    state['booking_ref'] = booking_ref
                    self.conversations[conversation_id] = state

                    return f"💰 {state['type']} man & van at {state['postcode']}: {state['price']} including V-A-T. Would you like to book this?"
                else:
                    return "Unable to get pricing for your area."
            except:
                return "Unable to get pricing for your area."

        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."


class GrabAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'grab'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()

        if any(word in message_lower for word in ['grab', 'grab hire', 'grab lorry']):
            data['service'] = 'grab'

            # EXACT SCRIPTS for grab terminology
            if any(term in message_lower for term in ['8-wheeler', '8 wheeler']):
                data['type'] = '16t'  # 8-wheeler = 16-tonne capacity
            elif any(term in message_lower for term in ['6-wheeler', '6 wheeler']):
                data['type'] = '12t'  # 6-wheeler = 12-tonne capacity
            elif any(size in message_lower for size in ['16-tonne', '16 tonne', '16t']):
                data['type'] = '16t'
            elif any(size in message_lower for size in ['12-tonne', '12 tonne', '12t']):
                data['type'] = '12t'
            else:
                data['type'] = '12t'  # Default to 6-wheeler (12-tonne)
        else:
            data['service'] = 'grab'
            data['type'] = '12t'  # Default

        return data

    def get_next_response(self, message, state, conversation_id):
        """PDF COMPLIANT Grab Hire Flow C1-C5"""
        
        # Check for specialist services first
        specialist_service = self.check_specialist_service(message)
        if specialist_service:
            return self.forward_rule(specialist_service, conversation_id)
        
        # MOST IMPORTANT: If user wants to book and we have pricing > 0
        wants_to_book = self.should_book(message)
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            try:
                price_num = float(str(state['price']).replace('£', '').replace(',', ''))
                if price_num > 0:
                    return self.complete_booking_proper(state)
            except:
                pass

        # C1: INFORMATION GATHERING (MANDATORY - ALL DETAILS FIRST)
        if not state.get('firstName'):
            return "Can I take your name please?"
        elif not state.get('phone'):
            return "What's the best phone number to contact you on?"
        elif not state.get('postcode'):
            return "What's the postcode where you need the grab lorry?"
        elif not state.get('service'):
            return "What type of materials do you have?"
        elif not any(word in ' '.join(state.get('messages', [])).lower() for word in ['tonne', 'tons', 'loads', 'cubic']):
            return "How much material do you have approximately?"

        # C2: GRAB SIZE UNDERSTANDING (EXACT SCRIPTS)
        if not state.get('size_confirmed'):
            if '8-wheeler' in message.lower():
                state['size_confirmed'] = True
                self.conversations[conversation_id] = state
                return "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry."
            elif '6-wheeler' in message.lower():
                state['size_confirmed'] = True
                self.conversations[conversation_id] = state
                return "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry."
            state['size_confirmed'] = True
            self.conversations[conversation_id] = state

        # C3: MATERIALS ASSESSMENT
        if not state.get('materials_assessed'):
            # Check for wait & load skip mention - IMMEDIATE transfer
            if any(term in message.lower() for term in ['wait & load', 'wait and load']):
                return self.forward_rule("wait & load skip availability and costs", conversation_id)
            
            # Check for mixed materials
            messages_text = ' '.join(state.get('messages', []))
            if (any(material in messages_text.lower() for material in ['soil', 'rubble', 'muck']) and
                any(other in messages_text.lower() for other in ['wood', 'metal', 'plastic', 'general'])):
                return self.forward_rule("mixed materials assessment", conversation_id)
            
            state['materials_assessed'] = True
            self.conversations[conversation_id] = state

        # C4: ACCESS & TIMING
        if not state.get('access_assessed'):
            if 'complex' in message.lower() or 'difficult' in message.lower():
                return self.forward_rule("complex access assessment", conversation_id)
            
            if not any(word in ' '.join(state.get('messages', [])).lower() for word in ['access', 'clear']):
                return "Is there clear access for the grab lorry?"
            
            state['access_assessed'] = True
            self.conversations[conversation_id] = state

        # If user wants to book but we don't have price yet
        if wants_to_book and not state.get('price'):
            return self.get_pricing_and_complete_booking(state, conversation_id)

        # Get pricing if all info collected but no price
        if not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)

        # C5: QUOTE & PRICING - Present quote
        if state.get('price'):
            try:
                price_num = float(str(state['price']).replace('£', '').replace(',', ''))
                if price_num > 0:
                    return f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']} including V-A-T. Would you like to book this?"
            except:
                pass

        return "How can I help you with grab hire?"

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """MOST IMPORTANT: Get pricing and complete booking immediately"""
        try:
            from utils.wasteking_api import create_booking, get_pricing

            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."

            booking_ref = booking_result['booking_ref']
            grab_type = state.get('type', '12t')

            price_result = get_pricing(booking_ref, state['postcode'], state['service'], grab_type)
            if not price_result.get('success'):
                return "Unable to get pricing for your area."

            price = price_result['price']
            
            # Check for pricing issues as per PDF
            try:
                price_num = float(str(price).replace('£', '').replace(',', ''))
                if price_num == 0 or price_num > 500:
                    return self.forward_rule("accurate grab pricing", conversation_id)
            except:
                return self.forward_rule("accurate grab pricing", conversation_id)

            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', grab_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state

                return self.complete_booking_proper(state)
            else:
                return "Unable to get pricing for your area."

        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and ask for booking"""
        try:
            from utils.wasteking_api import create_booking, get_pricing

            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."

            booking_ref = booking_result['booking_ref']
            grab_type = state.get('type', '12t')

            price_result = get_pricing(booking_ref, state['postcode'], state['service'], grab_type)
            if not price_result.get('success'):
                return "Unable to get pricing for your area."

            price = price_result['price']
            
            # Check for pricing issues as per PDF
            try:
                price_num = float(str(price).replace('£', '').replace(',', ''))
                if price_num == 0 or price_num > 500:
                    return self.forward_rule("accurate grab pricing", conversation_id)
            except:
                return self.forward_rule("accurate grab pricing", conversation_id)

            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', grab_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state

                return f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']} including V-A-T. Would you like to book this?"
            else:
                return "Unable to get pricing for your area."

        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."
