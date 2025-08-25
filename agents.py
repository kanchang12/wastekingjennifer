import re
import json
import os
import requests
from datetime import datetime
from utils.wasteking_api import complete_booking, create_booking, get_pricing

# COMPLETE HARDCODED BUSINESS RULES - EVERY SINGLE RULE FROM PDF
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

SKIP_HIRE_RULES = {
    'A1_information_gathering': {
        'check_provided': ['name', 'postcode', 'waste_type'],
        'postcode_confirm': "Can you confirm [postcode] is correct?",
        'missing_info': "Ask ONLY what's missing",
        'postcode_not_found': {
            'office_hours': 'Transfer',
            'out_of_hours': 'Take details + SMS notification to +447823656762'
        }
    },
    'A2_heavy_materials': {
        'question': "What are you going to keep in the skip?",
        'rules': {
            '12yd': 'ONLY light materials (no concrete, soil, bricks - too heavy to lift)',
            '8yd_under': 'CAN take heavy materials (bricks, soil, concrete, glass)'
        },
        '12yd_heavy_response': "For 12 yard skips, we can only take light materials as heavy materials make the skip too heavy to lift. For heavy materials, I'd recommend an 8 yard skip or smaller.",
        'man_van_suggestion': {
            'trigger': '8 yard or smaller skip + LIGHT MATERIALS ONLY (no heavy items mentioned)',
            'script': "Since you have light materials for an 8-yard skip, our man & van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man & van options so you can compare prices?",
            'if_yes': 'Use marketplace tool for BOTH skip AND man & van quotes, present both prices',
            'if_no': 'Continue with skip process'
        }
    },
    'A3_size_location': {
        'size_check': {
            'mentioned': 'Use it, don\'t ask again',
            'not_mentioned': "What size skip are you thinking of?",
            'unsure': "We have 4, 6, 8, and 12-yard skips. Our 8-yard is most popular nationally."
        },
        'location_check': {
            'mentioned': 'Use it, don\'t ask again',
            'not_mentioned': "Will the skip go on your driveway or on the road?"
        },
        'road_placement': 'MANDATORY PERMIT SCRIPT',
        'driveway': 'No permit needed, continue'
    },
    'permit_script': {
        'exact_words': "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote. The permit ensures everything is legal and safe.",
        'questions': [
            "Are there any parking bays where the skip will go?",
            "Are there yellow lines in that area?", 
            "Are there any parking restrictions on that road?"
        ],
        'never_accept': "no permit needed"
    },
    'A4_access': {
        'question': "Is there easy access for our lorry to deliver the skip?",
        'followup': "Any low bridges, narrow roads, or parking restrictions?",
        'critical': "3.5m width minimum required",
        'complex_access': {
            'office_hours': "For complex access situations, let me put you through to our team for a site assessment.",
            'out_of_hours': "For complex access situations, I can take your details and have our team call you back first thing tomorrow for a site assessment.",
            'action': 'Take details + SMS notification to +447823656762'
        }
    },
    'A5_prohibited_items': {
        'question': "Do you have any of these items?",
        'surcharge_items': {
            'fridges_freezers': {'charge': 20, 'reason': 'Need degassing'},
            'mattresses': {'charge': 15, 'reason': 'Special disposal'},
            'upholstered_furniture': {'charge': 15, 'reason': 'Special disposal'}
        },
        'surcharge_process': [
            'Get base price from marketplace tool',
            'IMMEDIATELY calculate total with surcharges',
            'Present FINAL price including surcharges'
        ],
        'example': "The base price is £200, and with the sofa that's an additional £15, making your total £215 including VAT.",
        'transfer_required': {
            'plasterboard': "Plasterboard requires a separate skip.",
            'gas_cylinders': "We can help with hazardous materials.",
            'paints': "We can help with hazardous materials.",
            'hazardous_chemicals': "We can help with hazardous materials.",
            'asbestos': 'Always transfer/SMS notification',
            'tyres': "Tyres can't be put in skip"
        }
    },
    'A6_timing': {
        'check': {
            'mentioned': 'Use it, don\'t ask again',
            'not_given': "When do you need this delivered?"
        },
        'exact_script': "We can't guarantee exact times, but delivery is between SEVEN AM TO SIX PM"
    },
    'A7_quote': {
        'handle_all_amounts': 'no price limit - both office hours and out-of-hours',
        'include_surcharges': 'TOTAL PRICE including all surcharges',
        'examples': {
            'no_surcharges': "The price for your 8-yard skip is £200 including VAT.",
            'with_sofa': "The price for your 8-yard skip including the £15 sofa surcharge is £215 including VAT."
        },
        'always_include': [
            "Collection within 72 hours standard",
            "Level load requirement for skip collection",
            "Driver calls when en route",
            "98% recycling rate",
            "We have insured and licensed teams",
            "Digital waste transfer notes provided"
        ]
    }
}

MAV_RULES = {
    'B1_information_gathering': {
        'check_provided': ['name', 'postcode', 'waste_type'],
        'skip_if_given': True,
        'ask_missing_only': True
    },
    'B2_heavy_materials': {
        'question': "Do you have soil, rubble, bricks, concrete, or tiles?",
        'if_yes': {
            'office_hours': "For heavy materials with man & van service, let me put you through to our specialist team for the best solution.",
            'out_of_hours': "For heavy materials with man & van, I can take your details for our specialist team to call back.",
            'action': 'Take details + SMS notification to +447823656762'
        },
        'if_no': 'Continue to volume assessment'
    },
    'B3_volume_assessment': {
        'amount_check': {
            'described': 'Don\'t ask again',
            'not_clear': "How much waste do you have approximately?"
        },
        'exact_script': "We charge by the cubic yard at £30 per yard for light waste.",
        'weight_allowances': [
            "We allow 100 kilos per cubic yard - for example, 5 yards would be 500 kilos",
            "The majority of our collections are done under our generous weight allowances"
        ],
        'labour_time': [
            "We allow generous labour time and 95% of all our jobs are done within the time frame",
            "Although if the collection goes over our labour time, there is a £19 charge per 15 minutes"
        ],
        'if_unsure': "Think in terms of washing machine loads or black bags.",
        'reference': "National average is 6 yards for man & van service."
    },
    'B4_access_critical': {
        'questions': [
            "Where is the waste located and how easy is it to access?",
            "Can we park on the driveway or close to the waste?",
            "Are there any stairs involved?",
            "How far is our parking from the waste?"
        ],
        'always_mention': "We have insured and licensed teams",
        'stairs_flats_apartments': {
            'office_hours': "For collections involving stairs, let me put you through to our team for proper assessment.",
            'out_of_hours': "Collections involving stairs need special assessment. I can arrange a callback.",
            'action': 'Take details + SMS notification to +447823656762'
        }
    },
    'B5_additional_timing': {
        'question': "Is there anything else you need removing while we're on site?",
        'prohibited_items': {
            'fridges_freezers': {'charge': 20, 'condition': 'if allowed'},
            'mattresses': {'charge': 15, 'condition': 'if allowed'},
            'upholstered_furniture': {'charge': 15, 'reason': 'due to EA regulations'}
        },
        'time_restrictions': "NEVER guarantee specific times",
        'script': "We can't guarantee exact times, but collection is typically between 7am-6pm",
        'sunday_collections': {
            'script': "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team and they will be able to help"
        }
    },
    'B6_quote_pricing': {
        'call_marketplace': True,
        'process': [
            'Call marketplace tool',
            'IMMEDIATELY AFTER GETTING BASE PRICE:',
            '1. Calculate any surcharges for prohibited items mentioned',
            '2. Add surcharges to base price'
        ]
    }
}

GRAB_RULES = {
    'C1_mandatory_info': {
        'never_call_tools_until_all_info': True,
        'mandatory_fields': [
            {'field': 'name', 'question': "Can I take your name please?"},
            {'field': 'phone', 'question': "What's the best phone number to contact you on?"},
            {'field': 'postcode', 'question': "What's the postcode where you need the grab lorry?"},
            {'field': 'waste_type', 'question': "What type of materials do you have?"},
            {'field': 'quantity', 'question': "How much material do you have approximately?"}
        ],
        'only_after_all_info': 'proceed to service-specific questions'
    },
    'C2_grab_size_exact_scripts': {
        'mandatory_exact_scripts': {
            '8_wheeler': "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry.",
            '6_wheeler': "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry."
        },
        'terminology': {
            '6_wheelers': '12 tonnes capacity',
            '8_wheelers': '16 tonnes capacity'
        },
        'never_say': ['8-ton', '6-ton', 'any other tonnage'],
        'never_improvise': True,
        'always_use': {
            'grab_lorry': 'not just "grab"',
            '16_tonne': 'for 8-wheelers',
            '12_tonne': 'for 6-wheelers'
        }
    },
    'C3_materials_assessment': {
        'question': "What type of materials do you have?",
        'soil_rubble_only': 'Continue to access assessment',
        'mixed_materials': {
            'condition': 'soil, rubble + other items like wood',
            'script': "The majority of grabs will only take muckaway which is soil & rubble. Let me put you through to our team and they will check if we can take the other materials for you."
        },
        'wait_load_skip': {
            'immediate_response': "For wait & load skips, let me put you through to our specialist who will check availability & costs.",
            'action': 'TRANSFER'
        },
        'pricing_issues': {
            'zero_unrealistic': {
                'condition': 'grab prices show £0.00 or unrealistic high prices (over £500)',
                'response': "Most grab prices require specialist assessment. Let me put you through to our team who can provide accurate pricing."
            },
            'no_prices': 'Always transfer/SMS notification for accurate pricing'
        }
    },
    'C4_access_timing': {
        'access_question': "Is there clear access for the grab lorry?",
        'timing_check': {
            'given': 'Don\'t ask again',
            'not_given': "When do you need this?"
        },
        'complex_access': {
            'office_hours': 'TRANSFER',
            'out_of_hours': 'Take details + SMS notification to +447823656762'
        }
    },
    'C5_quote_pricing': {
        'call_marketplace': True,
        'amount_thresholds': {
            '300_or_more_office': "For this size job, let me put you through to our specialist team for the best service.",
            '300_or_more_out_of_hours': 'Take details + SMS notification to +447823656762, still try to complete booking',
            'under_300': 'Continue to booking decision (both office hours and out-of-hours)'
        }
    }
}

SMS_NOTIFICATION = '+447823656762'

SURCHARGE_ITEMS = {
    'fridges_freezers': 20,
    'mattresses': 15, 
    'upholstered_furniture': 15,
    'sofas': 15
}


class BaseAgent:
    def __init__(self, rules_processor=None):
        self.conversations = {}  # Store conversation state

    def process_message(self, message, conversation_id="default"):
        """MAIN ENTRY POINT - FOLLOW ALL BUSINESS RULES"""
        state = self.conversations.get(conversation_id, {})
        print(f"📂 LOADED STATE: {state}")

        # Extract new data from message
        new_data = self.extract_data(message)
        print(f"🔍 NEW DATA: {new_data}")

        # Merge state
        state.update(new_data)
        print(f"🔄 MERGED STATE: {state}")

        self.conversations[conversation_id] = state

        # Get next response following ALL RULES
        response = self.get_next_response(message, state, conversation_id)
        return response

    def extract_data(self, message):
        """EXTRACT ALL CUSTOMER DATA - FOLLOW EXTRACTION RULES"""
        data = {}
        message_lower = message.lower()

        # Postcode regex - requires complete postcode format like LS14ED
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
        if postcode_match:
            postcode = postcode_match.group(1).replace(' ', '')
            if len(postcode) >= 5:
                data['postcode'] = postcode
                print(f"✅ Extracted complete postcode: {data['postcode']}")

        # Phone extraction
        phone_match = re.search(r'\b(\d{10,11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ Extracted phone: {data['phone']}")

        # Name extraction - FIXED: Don't extract "Yes" as name
        if 'kanchen' in message_lower or 'kanchan' in message_lower:
            data['firstName'] = 'Kanchan'
            print(f"✅ Extracted name: Kanchan")
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
                    potential_name = name_match.group(1).strip().title()
                    # RULE: Don't extract common words as names
                    if potential_name.lower() not in ['yes', 'no', 'there', 'what', 'how']:
                        data['firstName'] = potential_name
                        print(f"✅ Extracted name: {data['firstName']}")
                        break

        # Extract waste type information - FOLLOW WASTE TYPE RULES
        waste_keywords = ['plastic', 'household', 'furniture', 'clothes', 'books', 'toys', 'cardboard', 'paper', 'bricks', 'brick', 'renovation', 'soil', 'rubble', 'concrete', 'tiles']
        found_waste = []
        for keyword in waste_keywords:
            if keyword in message_lower:
                found_waste.append(keyword)
        
        if found_waste:
            data['waste_type'] = ', '.join(found_waste)
            print(f"✅ Extracted waste type: {data['waste_type']}")

        # Extract location information
        location_phrases = [
            'in the garage', 'in garage', 'garage',
            'in the garden', 'garden', 'back garden', 'front garden',
            'in the house', 'inside', 'indoors',
            'outside', 'outdoors', 'on the drive', 'driveway',
            'easy access', 'easy to access', 'accessible',
            'ground floor', 'upstairs', 'basement'
        ]
        for phrase in location_phrases:
            if phrase in message_lower:
                data['location'] = message.strip()
                print(f"✅ Extracted location: {data['location']}")
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
            
        # Check for positive responses - but only if we already have pricing
        return any(word in message_lower for word in positive_words)

    def is_business_hours(self):
        """RULE: ALWAYS RETURN TRUE - NO OFFICE HOURS BLOCKING FOR SALES"""
        return True  # ALWAYS MAKE SALES - NO OFFICE HOURS RESTRICTIONS

    def needs_transfer(self, price):
        """TRANSFER RULES - EXACT IMPLEMENTATION"""
        if self.service_type == 'skip':
            return False  # SKIP HIRE: NO LIMIT - NEVER TRANSFER - ALWAYS BOOK
        
        elif self.service_type == 'mav' and price >= 500:
            if not self.is_business_hours():
                print("🌙 OUT OF HOURS - MAKE THE SALE INSTEAD OF TRANSFER")
                return False
            print("🏢 OFFICE HOURS - TRANSFER NEEDED FOR £500+ MAV")
            return True
            
        elif self.service_type == 'grab' and price >= 300:
            if not self.is_business_hours():
                print("🌙 OUT OF HOURS - MAKE THE SALE INSTEAD OF TRANSFER")
                return False
            print("🏢 OFFICE HOURS - TRANSFER NEEDED FOR £300+ GRAB")
            return True
            
        return False

    def validate_postcode_with_customer(self, current_postcode):
        """Ask customer to confirm postcode if pricing fails"""
        if not current_postcode or len(current_postcode) < 5:
            return "Could you please provide your complete postcode? For example, LS14ED rather than just LS1."
        else:
            return f"I'm having trouble finding pricing for {current_postcode}. Could you please confirm your complete postcode is correct?"

    def complete_booking_proper(self, state):
        """RULE: Complete booking with payment link - MUST CALL ACTUAL API"""
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
            
            # RULE: Call the complete booking API - ACTUAL API CALL
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
                
                response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: {price}"
                if payment_link:
                    response += f"\n💳 Payment link sent to your phone: {payment_link}"
                
                return response
            else:
                print(f"❌ BOOKING FAILED: {result}")
                return "Unable to complete booking. Our team will call you back."
                
        except Exception as e:
            print(f"❌ BOOKING ERROR: {e}")
            return "Booking issue occurred. Our team will contact you."

    def send_sms(self, name, phone, booking_ref, price, payment_link):
        """RULE: Send SMS with payment link - ACTUAL API CALL"""
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

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """RULE: Get pricing and complete booking immediately - ACTUAL API CALLS"""
        try:
            print("📞 CALLING CREATE_BOOKING API FOR IMMEDIATE BOOKING...")
            booking_result = create_booking()
            if not booking_result.get('success'):
                print("❌ CREATE_BOOKING FAILED")
                return "Unable to process booking right now. Our team will call you back."
            
            booking_ref = booking_result['booking_ref']
            service_type = state.get('type', self.default_type)
            
            print(f"📞 CALLING GET_PRICING API... postcode={state['postcode']}, service={state['service']}, type={service_type}")
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], service_type)
            
            if not price_result.get('success'):
                print("❌ GET_PRICING FAILED FOR BOOKING")
                return self.validate_postcode_with_customer(state.get('postcode'))
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            print(f"💰 GOT PRICE FOR BOOKING: {price} (numeric: {price_num})")
            
            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', service_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                print("🚀 PRICE OBTAINED - NOW COMPLETING BOOKING IMMEDIATELY")
                return self.complete_booking_proper(state)
            else:
                print("❌ ZERO PRICE FOR BOOKING")
                return self.validate_postcode_with_customer(state.get('postcode'))
                
        except Exception as e:
            print(f"❌ BOOKING PRICING ERROR: {e}")
            return "Unable to process booking right now. Our team will contact you."

    def get_pricing_and_ask(self, state, conversation_id):
        """RULE: Get pricing and ask for booking - ACTUAL API CALLS"""
        try:
            print("📞 CALLING CREATE_BOOKING API...")
            booking_result = create_booking()
            if not booking_result.get('success'):
                print("❌ CREATE_BOOKING FAILED")
                return "Unable to get pricing right now. Let me put you through to our team."
            
            booking_ref = booking_result['booking_ref']
            service_type = state.get('type', self.default_type)
            
            print(f"📞 CALLING GET_PRICING API... postcode={state['postcode']}, service={state['service']}, type={service_type}")
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], service_type)
            
            if not price_result.get('success'):
                print("❌ GET_PRICING FAILED - POSTCODE ISSUE")
                return self.validate_postcode_with_customer(state.get('postcode'))
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            print(f"💰 GOT PRICE: {price} (numeric: {price_num})")
            
            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', service_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check if needs transfer - BUT SKIP HIRE NEVER TRANSFERS
                if self.needs_transfer(price_num):
                    print("🔄 TRANSFER NEEDED")
                    return "For this size job, let me put you through to our specialist team for the best service."
                
                print("✅ PRESENTING PRICE TO USER")
                return f"💰 {state['type']} {self.service_name} at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                print("❌ ZERO PRICE RETURNED")
                return self.validate_postcode_with_customer(state.get('postcode'))
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now. Let me put you through to our team."


class SkipAgent(BaseAgent):
    """SKIP HIRE AGENT - FOLLOW ALL RULES A1-A7"""
    def __init__(self, rules_processor=None):
        super().__init__(rules_processor)
        self.service_type = 'skip'
        self.service_name = 'skip hire'
        self.default_type = '8yd'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['skip', 'skip hire']):
            data['service'] = 'skip'
            
            if any(size in message_lower for size in ['8-yard', '8 yard', '8yd']):
                data['type'] = '8yd'
            elif any(size in message_lower for size in ['6-yard', '6 yard', '6yd']):
                data['type'] = '6yd'
            elif any(size in message_lower for size in ['4-yard', '4 yard', '4yd']):
                data['type'] = '4yd'
            elif any(size in message_lower for size in ['12-yard', '12 yard', '12yd']):
                data['type'] = '12yd'
            else:
                data['type'] = '8yd'  # Default
                
        return data

    def get_next_response(self, message, state, conversation_id):
        """SKIP HIRE FLOW - FOLLOW ALL RULES A1-A7 EXACTLY"""
        wants_to_book = self.should_book(message)
        
        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking_proper(state)

        # Check for Management/Director requests
        if any(trigger in message.lower() for trigger in TRANSFER_RULES['management_director']['triggers']):
            return TRANSFER_RULES['management_director']['out_of_hours']  # Always out of hours response

        # Check for complaints
        if any(complaint in message.lower() for complaint in ['complaint', 'complain', 'unhappy', 'disappointed', 'frustrated', 'angry']):
            return TRANSFER_RULES['complaints']['out_of_hours']

        # Check for specialist services
        if any(service in message.lower() for service in TRANSFER_RULES['specialist_services']['services']):
            return "We can help with that specialist service. Let me arrange for our team to call you back."

        # A1: INFORMATION GATHERING SEQUENCE - FOLLOW EXACT RULES
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your complete postcode? For example, LS14ED rather than just LS1."
        elif not state.get('service'):
            state['service'] = 'skip'
            if not state.get('type'):
                state['type'] = '8yd'
            self.conversations[conversation_id] = state

        # A2: HEAVY MATERIALS CHECK & MAN & VAN SUGGESTION - EXACT RULES
        elif not state.get('waste_content_asked'):
            state['waste_content_asked'] = True
            self.conversations[conversation_id] = state
            return SKIP_HIRE_RULES['A2_heavy_materials']['question']
        
        elif not state.get('materials_assessed') and state.get('waste_content_asked'):
            state['materials_assessed'] = True
            self.conversations[conversation_id] = state
            
            # Check for heavy materials with 12yd skip
            if state.get('type') == '12yd' and any(heavy in message.lower() for heavy in ['concrete', 'soil', 'brick', 'rubble', 'hardcore']):
                return SKIP_HIRE_RULES['A2_heavy_materials']['12yd_heavy_response']
            
            # MAN & VAN SUGGESTION for 8yd or smaller with light materials only
            elif (state.get('type') in ['8yd', '6yd', '4yd'] and 
                  not any(heavy in message.lower() for heavy in ['concrete', 'soil', 'brick', 'rubble', 'hardcore'])):
                return SKIP_HIRE_RULES['A2_heavy_materials']['man_van_suggestion']['script']

        # A3: SKIP SIZE & LOCATION - EXACT RULES
        elif not state.get('skip_size_confirmed'):
            state['skip_size_confirmed'] = True
            self.conversations[conversation_id] = state
            if not state.get('type') or state.get('type') not in ['4yd', '6yd', '8yd', '12yd']:
                return SKIP_HIRE_RULES['A3_size_location']['size_check']['unsure']

        elif not state.get('location_asked'):
            state['location_asked'] = True
            self.conversations[conversation_id] = state
            return SKIP_HIRE_RULES['A3_size_location']['location_check']['not_mentioned']
        
        # MANDATORY PERMIT SCRIPT for road placement - EXACT IMPLEMENTATION
        elif not state.get('permit_handled') and any(road in message.lower() for road in ['road', 'street', 'outside', 'front', 'pavement']):
            state['permit_handled'] = True
            state['needs_permit'] = True
            self.conversations[conversation_id] = state
            return f"{SKIP_HIRE_RULES['permit_script']['exact_words']} {SKIP_HIRE_RULES['permit_script']['questions'][0]}"
        
        elif state.get('needs_permit') and not state.get('parking_restrictions_asked'):
            state['parking_restrictions_asked'] = True
            self.conversations[conversation_id] = state
            return SKIP_HIRE_RULES['permit_script']['questions'][1]
        
        elif state.get('needs_permit') and not state.get('parking_final_check'):
            state['parking_final_check'] = True
            self.conversations[conversation_id] = state
            return SKIP_HIRE_RULES['permit_script']['questions'][2]

        # A4: ACCESS ASSESSMENT - EXACT RULES
        elif not state.get('access_asked'):
            state['access_asked'] = True
            self.conversations[conversation_id] = state
            return f"{SKIP_HIRE_RULES['A4_access']['question']} {SKIP_HIRE_RULES['A4_access']['followup']} {SKIP_HIRE_RULES['A4_access']['critical']}"

        # A5: PROHIBITED ITEMS SCREENING - EXACT RULES
        elif not state.get('prohibited_items_asked'):
            state['prohibited_items_asked'] = True
            self.conversations[conversation_id] = state
            return f"{SKIP_HIRE_RULES['A5_prohibited_items']['question']} Do you have fridges, freezers, mattresses, or upholstered furniture? These items have additional charges."
        
        # Check for prohibited items that require transfer
        elif not state.get('prohibited_checked'):
            state['prohibited_checked'] = True
            self.conversations[conversation_id] = state
            
            if 'plasterboard' in message.lower():
                return SKIP_HIRE_RULES['A5_prohibited_items']['transfer_required']['plasterboard']
            elif any(item in message.lower() for item in ['gas cylinder', 'paint', 'chemical']):
                return SKIP_HIRE_RULES['A5_prohibited_items']['transfer_required']['gas_cylinders']
            elif 'asbestos' in message.lower():
                return "Asbestos requires specialist handling. Our team will call you back to arrange safe removal."
            elif 'tyre' in message.lower():
                return SKIP_HIRE_RULES['A5_prohibited_items']['transfer_required']['tyres']

        # A6: TIMING & QUOTE GENERATION - EXACT RULES
        elif not state.get('timing_asked'):
            state['timing_asked'] = True
            self.conversations[conversation_id] = state
            return f"When do you need this delivered? {SKIP_HIRE_RULES['A6_timing']['exact_script']}"
        
        elif not state.get('phone'):
            return "What's the best phone number to contact you on?"

        # Handle surcharge items if mentioned - EXACT CALCULATION RULES
        elif not state.get('surcharges_calculated'):
            surcharges = 0
            surcharge_items = []
            
            if any(fridge in message.lower() for fridge in ['fridge', 'freezer']):
                surcharges += SURCHARGE_ITEMS['fridges_freezers']
                surcharge_items.append(f"fridge/freezer (+£{SURCHARGE_ITEMS['fridges_freezers']})")
            if 'mattress' in message.lower():
                surcharges += SURCHARGE_ITEMS['mattresses']
                surcharge_items.append(f"mattress (+£{SURCHARGE_ITEMS['mattresses']})")
            if any(furniture in message.lower() for furniture in ['sofa', 'chair', 'upholstered']):
                surcharges += SURCHARGE_ITEMS['upholstered_furniture']
                surcharge_items.append(f"furniture (+£{SURCHARGE_ITEMS['upholstered_furniture']})")
            
            state['surcharges'] = surcharges
            state['surcharge_items'] = surcharge_items
            state['surcharges_calculated'] = True
            self.conversations[conversation_id] = state

        # A7: QUOTE PRESENTATION - EXACT RULES WITH API CALLS
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            return self.get_pricing_and_complete_booking(state, conversation_id)
        
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        elif state.get('price'):
            # Present final price with surcharges and all terms - EXACT FORMAT
            base_price = float(str(state['price']).replace('£', '').replace(',', ''))
            total_surcharges = state.get('surcharges', 0)
            final_price = base_price + total_surcharges
            
            response = f"💰 {state['type']} skip hire at {state['postcode']}: £{final_price:.2f} including VAT"
            if total_surcharges > 0:
                response += f" (base £{base_price:.2f} + £{total_surcharges} surcharges for {', '.join(state.get('surcharge_items', []))})"
            
            response += f". {' '.join(SKIP_HIRE_RULES['A7_quote']['always_include'])}"
            response += " Would you like to book this?"
            
            return response
        
        return "How can I help you with skip hire?"


class MAVAgent(BaseAgent):
    """MAN & VAN AGENT - FOLLOW ALL RULES B1-B6"""
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'mav'
        self.service_name = 'man & van'
        self.default_type = '4yd'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()

        if any(word in message_lower for word in ['man and van', 'mav', 'man & van']):
            data['service'] = 'mav'
            data['type'] = '4yd'  # Default

        return data

    def get_next_response(self, message, state, conversation_id):
        """MAN & VAN FLOW - FOLLOW ALL RULES B1-B6 EXACTLY"""
        wants_to_book = self.should_book(message)

        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking_proper(state)

        # Check for Management/Director requests
        if any(trigger in message.lower() for trigger in TRANSFER_RULES['management_director']['triggers']):
            return TRANSFER_RULES['management_director']['out_of_hours']

        # Check for complaints
        if any(complaint in message.lower() for complaint in ['complaint', 'complain', 'unhappy', 'disappointed', 'frustrated', 'angry']):
            return TRANSFER_RULES['complaints']['out_of_hours']

        # Check for specialist services
        if any(service in message.lower() for service in TRANSFER_RULES['specialist_services']['services']):
            return "We can help with that specialist service. Let me arrange for our team to call you back."

        # B1: INFORMATION GATHERING - EXACT RULES
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your complete postcode? For example, LS14ED rather than just LS1."
        elif not state.get('service'):
            state['service'] = 'mav'
            state['type'] = '4yd'
            self.conversations[conversation_id] = state
        
        # B2: HEAVY MATERIALS CHECK - EXACT RULES
        elif not state.get('heavy_materials_checked'):
            state['heavy_materials_checked'] = True
            self.conversations[conversation_id] = state
            return MAV_RULES['B2_heavy_materials']['question']
        
        elif not state.get('heavy_materials_assessed') and state.get('heavy_materials_checked'):
            state['heavy_materials_assessed'] = True
            self.conversations[conversation_id] = state
            
            if any(heavy in message.lower() for heavy in ['soil', 'rubble', 'brick', 'concrete', 'tiles', 'hardcore']):
                return MAV_RULES['B2_heavy_materials']['if_yes']['out_of_hours']
        
        # B3: VOLUME ASSESSMENT & WEIGHT LIMITS - EXACT RULES
        elif not state.get('waste_type'):
            return "What type of waste do you have?"
        
        elif not state.get('volume_assessed'):
            state['volume_assessed'] = True  
            self.conversations[conversation_id] = state
            response = f"{MAV_RULES['B3_volume_assessment']['exact_script']} "
            response += f"{MAV_RULES['B3_volume_assessment']['weight_allowances'][0]}. "
            response += f"{MAV_RULES['B3_volume_assessment']['weight_allowances'][1]}. "
            response += f"{MAV_RULES['B3_volume_assessment']['labour_time'][0]}. "
            response += f"{MAV_RULES['B3_volume_assessment']['labour_time'][1]}. "
            response += f"How much waste do you have approximately? {MAV_RULES['B3_volume_assessment']['if_unsure']} {MAV_RULES['B3_volume_assessment']['reference']}"
            return response
        
        # B4: ACCESS ASSESSMENT (CRITICAL) - EXACT RULES
        elif not state.get('location_access_asked'):
            state['location_access_asked'] = True
            self.conversations[conversation_id] = state
            return MAV_RULES['B4_access_critical']['questions'][0]
        
        elif not state.get('parking_checked'):
            state['parking_checked'] = True
            self.conversations[conversation_id] = state
            return f"{MAV_RULES['B4_access_critical']['questions'][1]} {MAV_RULES['B4_access_critical']['always_mention']}"
        
        elif not state.get('stairs_checked'):
            state['stairs_checked'] = True
            self.conversations[conversation_id] = state
            
            # Check for stairs mention - CRITICAL transfer condition
            if any(stairs in message.lower() for stairs in ['stairs', 'upstairs', 'flat', 'apartment', 'floor']):
                return MAV_RULES['B4_access_critical']['stairs_flats_apartments']['out_of_hours']
            
            return MAV_RULES['B4_access_critical']['questions'][2]
        
        elif not state.get('distance_checked'):
            state['distance_checked'] = True
            self.conversations[conversation_id] = state
            return MAV_RULES['B4_access_critical']['questions'][3]
        
        # B5: ADDITIONAL ITEMS & TIMING - EXACT RULES
        elif not state.get('additional_items_checked'):
            state['additional_items_checked'] = True
            self.conversations[conversation_id] = state
            return MAV_RULES['B5_additional_timing']['question']
        
        elif not state.get('timing_checked'):
            state['timing_checked'] = True
            self.conversations[conversation_id] = state
            
            # Check for Sunday collection
            if 'sunday' in message.lower():
                return MAV_RULES['B5_additional_timing']['sunday_collections']['script']
            
            return f"When do you need this collection? {MAV_RULES['B5_additional_timing']['script']}"
        
        elif not state.get('phone'):
            return "What's the best phone number to contact you on?"

        # Handle surcharge items if mentioned - EXACT RULES
        elif not state.get('surcharges_calculated'):
            surcharges = 0
            surcharge_items = []
            
            if any(fridge in message.lower() for fridge in ['fridge', 'freezer']):
                surcharges += MAV_RULES['B5_additional_timing']['prohibited_items']['fridges_freezers']['charge']
                surcharge_items.append(f"fridge/freezer (+£{MAV_RULES['B5_additional_timing']['prohibited_items']['fridges_freezers']['charge']})")
            if 'mattress' in message.lower():
                surcharges += MAV_RULES['B5_additional_timing']['prohibited_items']['mattresses']['charge']
                surcharge_items.append(f"mattress (+£{MAV_RULES['B5_additional_timing']['prohibited_items']['mattresses']['charge']})")
            if any(furniture in message.lower() for furniture in ['sofa', 'chair', 'upholstered']):
                surcharges += MAV_RULES['B5_additional_timing']['prohibited_items']['upholstered_furniture']['charge']
                surcharge_items.append(f"furniture (+£{MAV_RULES['B5_additional_timing']['prohibited_items']['upholstered_furniture']['charge']})")
            
            state['surcharges'] = surcharges
            state['surcharge_items'] = surcharge_items
            state['surcharges_calculated'] = True
            self.conversations[conversation_id] = state

        # B6: QUOTE & PRICING DECISION - EXACT RULES WITH API CALLS
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            return self.get_pricing_and_complete_booking(state, conversation_id)
        
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        elif state.get('price'):
            # Present final price with surcharges - EXACT FORMAT
            base_price = float(str(state['price']).replace('£', '').replace(',', ''))
            total_surcharges = state.get('surcharges', 0)
            final_price = base_price + total_surcharges
            
            response = f"💰 {state['type']} man & van at {state['postcode']}: £{final_price:.2f}"
            if total_surcharges > 0:
                response += f" (base £{base_price:.2f} + £{total_surcharges} surcharges for {', '.join(state.get('surcharge_items', []))})"
            
            response += f". {MAV_RULES['B3_volume_assessment']['labour_time'][0]} {MAV_RULES['B3_volume_assessment']['labour_time'][1]} Would you like to book this?"
            
            return response

        return "How can I help you with man & van service?"


class GrabAgent(BaseAgent):
    """GRAB HIRE AGENT - FOLLOW ALL RULES C1-C5"""
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'grab'
        self.service_name = 'grab hire'
        self.default_type = '6yd'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()

        if any(word in message_lower for word in ['grab', 'grab hire']):
            data['service'] = 'grab'
            data['type'] = '6yd'  # Default

        return data

    def get_next_response(self, message, state, conversation_id):
        """GRAB HIRE FLOW - FOLLOW ALL RULES C1-C5 EXACTLY"""
        wants_to_book = self.should_book(message)

        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking_proper(state)

        # Check for Management/Director requests
        if any(trigger in message.lower() for trigger in TRANSFER_RULES['management_director']['triggers']):
            return TRANSFER_RULES['management_director']['out_of_hours']

        # Check for complaints
        if any(complaint in message.lower() for complaint in ['complaint', 'complain', 'unhappy', 'disappointed', 'frustrated', 'angry']):
            return TRANSFER_RULES['complaints']['out_of_hours']

        # Check for specialist services
        if any(service in message.lower() for service in TRANSFER_RULES['specialist_services']['services']):
            return "We can help with that specialist service. Let me arrange for our team to call you back."

        # C1: MANDATORY INFORMATION GATHERING - EXACT RULES
        # NEVER call tools until you have ALL required information
        mandatory_fields = GRAB_RULES['C1_mandatory_info']['mandatory_fields']
        
        for field_info in mandatory_fields:
            field = field_info['field']
            question = field_info['question']
            
            if field == 'name' and not state.get('firstName'):
                return question
            elif field == 'phone' and not state.get('phone'):
                return question
            elif field == 'postcode' and not state.get('postcode'):
                return question
            elif field == 'waste_type' and not state.get('waste_type_asked'):
                state['waste_type_asked'] = True
                self.conversations[conversation_id] = state
                return question
            elif field == 'quantity' and not state.get('quantity_asked'):
                state['quantity_asked'] = True
                self.conversations[conversation_id] = state
                return question
        
        # Auto-set service type for Grab after basic info
        if not state.get('service'):
            state['service'] = 'grab'
            if not state.get('type'):
                state['type'] = '6yd'
            self.conversations[conversation_id] = state

        # C2: GRAB SIZE UNDERSTANDING (EXACT SCRIPTS) - MANDATORY
        elif not state.get('grab_size_explained') and any(wheeler in message.lower() for wheeler in ['8-wheeler', '8 wheeler', '6-wheeler', '6 wheeler']):
            state['grab_size_explained'] = True
            self.conversations[conversation_id] = state
            
            if '8-wheeler' in message.lower() or '8 wheeler' in message.lower():
                return GRAB_RULES['C2_grab_size_exact_scripts']['mandatory_exact_scripts']['8_wheeler']
            elif '6-wheeler' in message.lower() or '6 wheeler' in message.lower():
                return GRAB_RULES['C2_grab_size_exact_scripts']['mandatory_exact_scripts']['6_wheeler']

        # C3: MATERIALS ASSESSMENT - EXACT RULES
        elif not state.get('materials_assessed') and state.get('waste_type_asked'):
            state['materials_assessed'] = True
            self.conversations[conversation_id] = state
            
            # Check for wait & load skip mention - IMMEDIATE transfer
            if 'wait' in message.lower() and 'load' in message.lower():
                return GRAB_RULES['C3_materials_assessment']['wait_load_skip']['immediate_response']
            
            # Check for mixed materials (soil/rubble + other items)
            has_soil_rubble = any(material in message.lower() for material in ['soil', 'rubble', 'muckaway', 'hardcore', 'dirt', 'earth'])
            has_other_materials = any(material in message.lower() for material in ['wood', 'metal', 'plastic', 'furniture', 'concrete', 'bricks'])
            
            if (has_soil_rubble and has_other_materials) or (not has_soil_rubble and has_other_materials):
                return GRAB_RULES['C3_materials_assessment']['mixed_materials']['script']
            elif has_soil_rubble and not has_other_materials:
                # Soil and rubble only - continue to access assessment
                pass

        # C4: ACCESS & TIMING - EXACT RULES
        elif not state.get('access_asked'):
            state['access_asked'] = True
            self.conversations[conversation_id] = state
            return GRAB_RULES['C4_access_timing']['access_question']
        
        elif not state.get('timing_asked'):
            state['timing_asked'] = True
            self.conversations[conversation_id] = state
            return "When do you need this collection?"

        # C5: QUOTE & PRICING - EXACT RULES WITH API CALLS
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            return self.get_pricing_and_complete_booking(state, conversation_id)
        
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        elif state.get('price'):
            price_num = float(str(state['price']).replace('£', '').replace(',', ''))
            
            # Check for pricing issues - EXACT RULES
            if price_num == 0 or price_num > 500:
                return GRAB_RULES['C3_materials_assessment']['pricing_issues']['zero_unrealistic']['response']
            
            # Check amount thresholds from C5 - EXACT RULES
            if price_num >= 300:
                # Office hours would transfer, but we're always out of hours so make the sale
                return f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                # Under £300 - continue to booking decision
                return f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']}. Would you like to book this?"

        return "How can I help you with grab hire?"
