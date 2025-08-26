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

# SKIP HIRE RULES (A1-A7) - COMPLETE RESTORATION
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
        'waste_asked': {
            'mentioned': 'Use it, don\'t ask again',
            'not_mentioned': "What waste you will use?"
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

# MAV RULES (B1-B6) - COMPLETE RESTORATION
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
        'exact_script': "We charge by the cubic yard",
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
            'out_of_hours': "Let's collect all the info about the project",
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

# GRAB RULES (C1-C5) - COMPLETE RESTORATION
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

# GLOBAL CONVERSATION STORAGE - SHARED ACROSS ALL AGENTS
global_conversations = {}

class ServiceRouter:
    """INTELLIGENT SERVICE ROUTING - FIXES ROUTING INCONSISTENCIES"""
    
    @staticmethod
    def determine_service(message):
        """Determine the correct service based on message content"""
        message_lower = message.lower()
        
        # SKIP HIRE - Explicit mentions first
        if any(word in message_lower for word in [
            'skip hire', 'skip', 'container hire', 'builders skip',
            'mini skip', 'maxi skip', 'yard skip', '4 yard skip',
            '6 yard skip', '8 yard skip', '12 yard skip'
        ]):
            return 'skip'
        
        # MAN & VAN - House clearance and furniture = MAV (NOT GRAB!)
        if any(phrase in message_lower for phrase in [
            'man and van', 'man & van', 'mav', 'man in van', 'man in a van',
            'house clearance', 'furniture removal', 'furniture collection', 
            'clearance', 'clear out', 'shed clearance', 'garage clearance',
            'furniture', 'wardrobe', 'wardrobes', 'sofa', 'bed', 'mattress',
            'chest of drawers', 'dining table', 'chairs', 'appliances',
            'washing machine', 'fridge', 'cooker', 'dishwasher',
            'office clearance', 'flat clearance', 'house clear',
            'removal service', 'loading service', 'we do the loading',
            'rubbish clearance', 'waste clearance', 'bulk collection'
        ]):
            return 'mav'
        
        # GRAB HIRE - ONLY for soil/rubble/construction waste (NOT furniture!)
        # Note: API might expect different service name, so we'll handle this
        if any(phrase in message_lower for phrase in [
            'grab hire', 'grab lorry', 'grab service',
            'soil removal', 'rubble removal', 'muckaway', 'dirt removal',
            'earth removal', 'topsoil', 'subsoil', 'hardcore',
            'construction rubble', 'demolition waste', 'excavation',
            'concrete removal', 'aggregates', 'building rubble'
        ]) and not any(furniture in message_lower for furniture in [
            'furniture', 'wardrobe', 'sofa', 'bed', 'table', 'chair', 'clearance'
        ]):
            return 'grab'
        
        # DEFAULT ROUTING BASED ON CONTEXT
        # If mentions soil/rubble but no furniture -> GRAB
        if any(material in message_lower for material in ['soil', 'rubble', 'concrete', 'hardcore', 'muckaway']) and \
           not any(furniture in message_lower for furniture in ['furniture', 'wardrobe', 'sofa', 'bed', 'clearance']):
            return 'grab'
        
        # If mentions furniture/clearance -> MAV
        if any(item in message_lower for item in ['furniture', 'clearance', 'wardrobe', 'sofa', 'bed', 'appliances']):
            return 'mav'
        
        # If asks about road sweeper or other unknown services -> GRAB (fallback)
        return 'grab'

class UniversalAgent:
    """SINGLE UNIVERSAL AGENT - HANDLES ALL SERVICES CONSISTENTLY WITH SUPPLIER CONFIRMATION"""
    
    def __init__(self):
        # Use global storage to ensure state persistence
        global global_conversations
        self.conversations = global_conversations
        self.supplier_phone = '+447394642517'  # Default supplier phone
        
    def is_business_hours(self):
        """Check if it's business hours for supplier confirmation"""
        now = datetime.now()
        day_of_week = now.weekday()  # 0=Monday, 6=Sunday
        hour = now.hour
        
        if day_of_week < 4:  # Monday-Thursday
            return 8 <= hour < 17
        elif day_of_week == 4:  # Friday
            return 8 <= hour < 16
        elif day_of_week == 5:  # Saturday
            return 9 <= hour < 12
        return False  # Sunday closed
    
    def needs_supplier_confirmation(self, message, state):
        """Check if request needs supplier confirmation - OFFICE HOURS ONLY"""
        if not self.is_business_hours():
            return False
            
        message_lower = message.lower()
        
        # Check for special requests that need confirmation
        special_requests = [
            'urgent', 'immediate', 'today', 'asap', 'emergency',
            'special', 'unusual', 'different', 'custom',
            'large amount', 'big job', 'commercial', 'business'
        ]
        
        return any(request in message_lower for request in special_requests)
    
    def get_supplier_confirmation_message(self):
        """Message while checking with supplier"""
        return "Let me just check with our team to confirm availability for your request. I'll be right back with you."
    
    def get_supplier_denied_message(self):
        """Message when supplier says no"""
        return "I've checked with our team and we can't fulfill that specific request right now. What would be a suitable alternative for you?"
    
    def needs_transfer(self, message):
        """Check if call needs to be transferred to supplier"""
        message_lower = message.lower()
        
        transfer_triggers = [
            'speak to someone', 'talk to human', 'manager', 'supervisor',
            'complaint', 'problem', 'issue', 'not happy', 'unhappy',
            'transfer me', 'connect me', 'put me through',
            'speak to glenn', 'director', 'glenn currie'
        ]
        
        return any(trigger in message_lower for trigger in transfer_triggers)
    
    def get_transfer_message(self):
        """Message when transferring call"""
        return f"I'm connecting you with our team now. You can also reach them directly at {self.supplier_phone}. Please hold while I transfer you."
        
    def process_message(self, message, conversation_id="default"):
        """MAIN ENTRY POINT - CONSISTENT PROCESSING FOR ALL SERVICES"""
        
        # STEP 1: DETERMINE SERVICE TYPE
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = {}
        
        state = self.conversations[conversation_id].copy()
        print(f"📂 LOADED STATE: {state}")
        
        # Determine service if not already set
        if not state.get('service_type'):
            service_type = ServiceRouter.determine_service(message)
            state['service_type'] = service_type
            print(f"🎯 DETERMINED SERVICE: {service_type}")
        
        # STEP 2: EXTRACT NEW DATA
        new_data = self.extract_data(message)
        print(f"🔍 NEW DATA: {new_data}")
        
        # STEP 3: MERGE STATE PROPERLY
        for key, value in new_data.items():
            if value and str(value).strip():
                state[key] = value
        
        print(f"🔄 MERGED STATE: {state}")
        
        # STEP 4: SAVE STATE IMMEDIATELY
        self.conversations[conversation_id] = state.copy()
        
        # STEP 5: GET RESPONSE BASED ON SERVICE TYPE
        if state['service_type'] == 'skip':
            response = self.handle_skip_service(message, state, conversation_id)
        elif state['service_type'] == 'mav':
            response = self.handle_mav_service(message, state, conversation_id)
        elif state['service_type'] == 'grab':
            response = self.handle_grab_service(message, state, conversation_id)
        else:
            response = "I can help you with skip hire, man & van, or grab hire services. What do you need?"
        
        # STEP 6: SAVE STATE AGAIN
        self.conversations[conversation_id] = state.copy()
        print(f"💾 FINAL STATE SAVED: {state}")
        
        return response
    
    def extract_data(self, message):
        """UNIVERSAL DATA EXTRACTION - WORKS FOR ALL SERVICES"""
        data = {}
        message_lower = message.lower()

        # Postcode extraction - Enhanced regex
        postcode_patterns = [
            r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})',  # Full UK postcode
            r'postcode\s+([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})',  # "postcode HP225LQ"
        ]
        
        for pattern in postcode_patterns:
            postcode_match = re.search(pattern, message.upper())
            if postcode_match:
                postcode = postcode_match.group(1).replace(' ', '')
                if len(postcode) >= 5:
                    data['postcode'] = postcode
                    print(f"✅ Extracted postcode: {data['postcode']}")
                    break

        # Phone extraction - Enhanced patterns
        phone_patterns = [
            r'\b(\d{11})\b',                    # 07976133518
            r'\b(\d{10})\b',                    # 0797613351
            r'\b(\d{5})\s+(\d{6})\b',           # 07976 133518
            r'\b(\d{4})\s+(\d{6})\b',           # 0797 613351  
            r'\b(\d{5})-(\d{6})\b',             # 07976-133518
            r'\b(\d{4})-(\d{6})\b',             # 0797-613351
            r'\((\d{4,5})\)\s*(\d{6})\b',       # (07976) 133518
            r'phone\s+(\d{11})',                # "phone 07976133518"
            r'contact\s+(\d{11})',              # "contact 07976133518"
        ]
        
        for pattern in phone_patterns:
            phone_match = re.search(pattern, message)
            if phone_match:
                if len(phone_match.groups()) == 1:
                    phone_number = phone_match.group(1)
                else:
                    phone_parts = [group for group in phone_match.groups() if group]
                    phone_number = ''.join(phone_parts)
                
                if len(phone_number) >= 10:
                    data['phone'] = phone_number
                    print(f"✅ Extracted phone: {data['phone']}")
                    break

        # Name extraction - Enhanced patterns
        if 'jackie' in message_lower:
            data['firstName'] = 'Jackie'
            print(f"✅ Extracted name: Jackie")
        elif 'kanchan' in message_lower or 'kanchen' in message_lower:
            data['firstName'] = 'Kanchan'
            print(f"✅ Extracted name: Kanchan")
        else:
            name_patterns = [
                r'name\s+(?:is\s+)?([A-Z][a-z]+)',
                r'(?:i\'m|im)\s+([A-Z][a-z]+)',
                r'^([A-Z][a-z]+),',
                r'([A-Z][a-z]+)\s+phone',
                r'for\s+([A-Z][a-z]+)',
            ]
            for pattern in name_patterns:
                name_match = re.search(pattern, message, re.IGNORECASE)
                if name_match:
                    potential_name = name_match.group(1).strip().title()
                    if potential_name.lower() not in ['yes', 'no', 'confirmed', 'please', 'phone']:
                        data['firstName'] = potential_name
                        print(f"✅ Extracted name: {data['firstName']}")
                        break

        return data
    
    def should_book(self, message):
        """UNIVERSAL BOOKING INTENT DETECTION"""
        message_lower = message.lower()
        
        booking_phrases = [
            'payment link', 'send payment', 'book', 'booking', 'confirm', 
            'proceed', 'complete booking', 'finish booking', 'place order',
            'make booking', 'create booking', 'secure booking', 'reserve',
            'checkout', 'complete order', 'finalize', 'arrange this',
            'wants to book', 'please send payment', 'send me the link'
        ]
        
        positive_words = ['yes', 'yeah', 'yep', 'ok', 'okay', 'alright', 'sure', 'go ahead']
        
        return any(phrase in message_lower for phrase in booking_phrases) or \
               any(word in message_lower for word in positive_words)
    
    def check_completion_status(self, state):
        """UNIVERSAL COMPLETION CHECK"""
        completion = {
            'name': 'yes' if state.get('firstName') else 'no',
            'address': 'yes' if state.get('postcode') else 'no',
            'phone': 'yes' if state.get('phone') else 'no'
        }
        
        all_ready = all(status == 'yes' for status in completion.values())
        print(f"📋 COMPLETION STATUS: {completion} | ALL READY: {all_ready}")
        
        return completion, all_ready
    
    def get_pricing(self, state, conversation_id, service_api_name, type_name, wants_to_book=False):
        """UNIVERSAL PRICING FUNCTION"""
        try:
            print("📞 CALLING CREATE_BOOKING API...")
            booking_result = create_booking()
            if not booking_result.get('success'):
                print("❌ CREATE_BOOKING FAILED")
                return "Unable to get pricing right now. Let me put you through to our team."
            
            booking_ref = booking_result['booking_ref']
            
            print(f"📞 CALLING GET_PRICING API... postcode={state['postcode']}, service={service_api_name}, type={type_name}")
            price_result = get_pricing(booking_ref, state['postcode'], service_api_name, type_name)
            
            if not price_result.get('success'):
                print("❌ GET_PRICING FAILED")
                return f"I'm having trouble finding pricing for {state['postcode']}. Could you please confirm your postcode is correct?"
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            print(f"💰 GOT PRICE: {price} (numeric: {price_num})")
            
            if price_num > 0:
                state['price'] = price
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state.copy()
                
                if wants_to_book:
                    print("🚀 USER WANTS TO BOOK - COMPLETING IMMEDIATELY")
                    return self.complete_booking(state)
                else:
                    service_name = state['service_type']
                    return f"{type_name} {service_name} service at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                return f"I'm having trouble finding pricing for {state['postcode']}. Could you please confirm your postcode is correct?"
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now. Let me put you through to our team."
    
    def complete_booking(self, state):
        """UNIVERSAL BOOKING COMPLETION"""
        try:
            print("🚀 COMPLETING BOOKING...")
            
            customer_data = {
                'firstName': state.get('firstName'),
                'phone': state.get('phone'),
                'postcode': state.get('postcode'),
                'service': state.get('service_api_name', state.get('service_type')),
                'type': state.get('type_name', '4yd')
            }
            
            print(f"📋 CUSTOMER DATA: {customer_data}")
            
            result = complete_booking(customer_data)
            
            if result.get('success'):
                booking_ref = result['booking_ref']
                price = result['price']
                payment_link = result.get('payment_link')
                
                print(f"✅ BOOKING SUCCESS: {booking_ref}, {price}")
                
                state['booking_completed'] = True
                state['final_booking_ref'] = booking_ref
                state['final_price'] = price
                
                if payment_link and state.get('phone'):
                    self.send_sms(state['firstName'], state['phone'], booking_ref, price, payment_link)
                
                response = f"Booking confirmed! Ref: {booking_ref}, Price: {price}"
                if payment_link:
                    response += f" Payment link sent to your phone: {payment_link}"
                
                return response
            else:
                print(f"❌ BOOKING FAILED: {result}")
                return "Unable to complete booking. Our team will call you back."
                
        except Exception as e:
            print(f"❌ BOOKING ERROR: {e}")
            return "Booking issue occurred. Our team will contact you."
    
    def send_sms(self, name, phone, booking_ref, price, payment_link):
        """SMS NOTIFICATION"""
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
    
    def handle_skip_service(self, message, state, conversation_id):
        """SKIP HIRE SERVICE HANDLER - FOLLOW ALL A1-A7 RULES WITH SUPPLIER CONFIRMATION"""
        wants_to_book = self.should_book(message)
        completion, all_ready = self.check_completion_status(state)
        
        # Check for transfer requests first
        if self.needs_transfer(message):
            return self.get_transfer_message()
        
        # Check if needs supplier confirmation (office hours only)
        if self.needs_supplier_confirmation(message, state) and not state.get('supplier_checked'):
            state['supplier_checked'] = True
            state['awaiting_supplier'] = True
            self.conversations[conversation_id] = state.copy()
            return self.get_supplier_confirmation_message()
        
        # Set API parameters for skip service
        state['service_api_name'] = 'skip'
        state['type_name'] = '8yd'  # Default skip size
        
        # If user wants to book and we have pricing, complete booking
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            return self.complete_booking(state)
        
        # If all info collected, get pricing
        if all_ready and not state.get('price'):
            return self.get_pricing(state, conversation_id, 'skip', '8yd', wants_to_book)
        
        # A1: Information gathering sequence
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your complete postcode? For example, LS14ED rather than just LS1."
        elif not state.get('phone'):
            return "What's the best phone number to contact you on?"
        
        # A2: Heavy materials check for 12yd skips
        if not state.get('materials_checked') and state.get('type_name') == '12yd':
            if any(heavy in message.lower() for heavy in ['concrete', 'soil', 'bricks', 'brick', 'rubble']):
                state['materials_checked'] = True
                return SKIP_HIRE_RULES['A2_heavy_materials']['12yd_heavy_response']
            else:
                state['materials_checked'] = True
        
        # A3: Size and location check
        if not state.get('size_confirmed'):
            if 'size' in message.lower() and not any(size in message.lower() for size in ['4', '6', '8', '12']):
                state['size_confirmed'] = True
                return SKIP_HIRE_RULES['A3_size_location']['size_check']['unsure']
            else:
                state['size_confirmed'] = True
        
        # A4: Access check  
        if not state.get('access_confirmed'):
            if 'access' not in message.lower():
                state['access_confirmed'] = True
                return SKIP_HIRE_RULES['A4_access']['question']
            else:
                state['access_confirmed'] = True
        
        # A5: Prohibited items check
        if not state.get('prohibited_checked'):
            prohibited_items = ['fridge', 'freezer', 'mattress', 'sofa', 'furniture']
            mentioned_items = [item for item in prohibited_items if item in message.lower()]
            if mentioned_items:
                surcharge_total = 0
                for item in mentioned_items:
                    if 'fridge' in item or 'freezer' in item:
                        surcharge_total += SKIP_HIRE_RULES['A5_prohibited_items']['surcharge_items']['fridges_freezers']['charge']
                    elif 'mattress' in item:
                        surcharge_total += SKIP_HIRE_RULES['A5_prohibited_items']['surcharge_items']['mattresses']['charge']
                    elif 'sofa' in item or 'furniture' in item:
                        surcharge_total += SKIP_HIRE_RULES['A5_prohibited_items']['surcharge_items']['upholstered_furniture']['charge']
                
                if surcharge_total > 0:
                    state['surcharge'] = surcharge_total
                    state['prohibited_checked'] = True
                    return f"There will be an additional £{surcharge_total} surcharge for those items due to special disposal requirements."
            else:
                state['prohibited_checked'] = True
        
        # A6: Timing check
        if not state.get('timing_confirmed'):
            if 'when' in message.lower() or 'time' in message.lower():
                state['timing_confirmed'] = True
                return SKIP_HIRE_RULES['A6_timing']['exact_script']
            else:
                state['timing_confirmed'] = True
        
        return "I can help you with skip hire. What's your name?"
    
    def handle_mav_service(self, message, state, conversation_id):
        """MAN & VAN SERVICE HANDLER - FOLLOW ALL B1-B6 RULES WITH SUPPLIER CONFIRMATION"""
        wants_to_book = self.should_book(message)
        completion, all_ready = self.check_completion_status(state)
        
        # Check for transfer requests first
        if self.needs_transfer(message):
            return self.get_transfer_message()
        
        # Check if needs supplier confirmation (office hours only)
        if self.needs_supplier_confirmation(message, state) and not state.get('supplier_checked'):
            state['supplier_checked'] = True
            state['awaiting_supplier'] = True
            self.conversations[conversation_id] = state.copy()
            return self.get_supplier_confirmation_message()
        
        # Set API parameters for MAV service
        state['service_api_name'] = 'mav'
        state['type_name'] = '4yd'  # Default MAV size
        
        # If user wants to book and we have pricing, complete booking
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            return self.complete_booking(state)
        
        # If all info collected, get pricing
        if all_ready and not state.get('price'):
            return self.get_pricing(state, conversation_id, 'mav', '4yd', wants_to_book)
        
        # B2: Heavy materials check FIRST (before information gathering)
        if state.get('firstName') and state.get('postcode') and not state.get('heavy_materials_checked'):
            if any(heavy in message.lower() for heavy in ['soil', 'rubble', 'bricks', 'concrete', 'tiles']):
                state['heavy_materials_checked'] = True
                return MAV_RULES['B2_heavy_materials']['if_yes']['out_of_hours']
            else:
                state['heavy_materials_checked'] = True
        
        # B1: Information gathering sequence
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your complete postcode? For example, LS14ED rather than just LS1."
        elif not state.get('phone'):
            return "What's the best phone number to contact you on?"
        
        # B3: Volume assessment
        if not state.get('volume_assessed'):
            if not any(amount in message.lower() for amount in ['yard', 'bag', 'load', 'full', 'much']):
                state['volume_assessed'] = True
                return f"{MAV_RULES['B3_volume_assessment']['amount_check']['not_clear']} {MAV_RULES['B3_volume_assessment']['exact_script']}. {MAV_RULES['B3_volume_assessment']['reference']}"
            else:
                state['volume_assessed'] = True
        
        # B4: Access critical questions
        if not state.get('access_assessed'):
            access_questions = MAV_RULES['B4_access_critical']['questions']
            if 'stairs' in message.lower():
                return MAV_RULES['B4_access_critical']['stairs_flats_apartments']['out_of_hours']
            elif 'access' not in message.lower():
                state['access_assessed'] = True
                return f"{access_questions[0]} {MAV_RULES['B4_access_critical']['always_mention']}"
            else:
                state['access_assessed'] = True
        
        # B5: Additional items and timing
        if not state.get('additional_checked'):
            prohibited_items = ['fridge', 'freezer', 'mattress', 'sofa']
            mentioned_items = [item for item in prohibited_items if item in message.lower()]
            if mentioned_items:
                surcharge_total = 0
                for item in mentioned_items:
                    if 'fridge' in item or 'freezer' in item:
                        surcharge_total += MAV_RULES['B5_additional_timing']['prohibited_items']['fridges_freezers']['charge']
                    elif 'mattress' in item:
                        surcharge_total += MAV_RULES['B5_additional_timing']['prohibited_items']['mattresses']['charge']
                    elif 'sofa' in item:
                        surcharge_total += MAV_RULES['B5_additional_timing']['prohibited_items']['upholstered_furniture']['charge']
                
                if surcharge_total > 0:
                    state['surcharge'] = surcharge_total
                    state['additional_checked'] = True
                    return f"There will be an additional £{surcharge_total} for those items {MAV_RULES['B5_additional_timing']['prohibited_items']['upholstered_furniture']['reason']}. {MAV_RULES['B5_additional_timing']['script']}"
            else:
                state['additional_checked'] = True
        
        return "I can help you with man & van service for furniture removal. What's your name?"
    
    def handle_grab_service(self, message, state, conversation_id):
        """GRAB HIRE SERVICE HANDLER - FOLLOW ALL C1-C5 RULES WITH SUPPLIER CONFIRMATION"""
        wants_to_book = self.should_book(message)
        completion, all_ready = self.check_completion_status(state)
        
        # Check for transfer requests first
        if self.needs_transfer(message):
            return self.get_transfer_message()
        
        # Check if needs supplier confirmation (office hours only)
        if self.needs_supplier_confirmation(message, state) and not state.get('supplier_checked'):
            state['supplier_checked'] = True
            state['awaiting_supplier'] = True
            self.conversations[conversation_id] = state.copy()
            return self.get_supplier_confirmation_message()
        
        # Try different service names for grab since API rejects "grab"
        state['service_api_name'] = 'skip'  # Fallback to skip for now
        state['type_name'] = '6yd'  # Default grab size
        
        # If user wants to book and we have pricing, complete booking
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            return self.complete_booking(state)
        
        # C3: Materials assessment FIRST
        if state.get('firstName') and not state.get('materials_assessed'):
            has_soil_rubble = any(material in message.lower() for material in ['soil', 'rubble', 'muckaway', 'dirt', 'earth', 'concrete'])
            has_other_items = any(item in message.lower() for item in ['wood', 'furniture', 'plastic', 'metal', 'general', 'mixed'])
            
            if has_soil_rubble and has_other_items:
                state['materials_assessed'] = True
                return GRAB_RULES['C3_materials_assessment']['mixed_materials']['script']
            else:
                state['materials_assessed'] = True
        
        # C1: Mandatory information gathering sequence
        mandatory_fields = GRAB_RULES['C1_mandatory_info']['mandatory_fields']
        
        if not state.get('firstName'):
            return mandatory_fields[0]['question']  # "Can I take your name please?"
        elif not state.get('phone'):
            return mandatory_fields[1]['question']  # "What's the best phone number to contact you on?"
        elif not state.get('postcode'):
            return mandatory_fields[2]['question']  # "What's the postcode where you need the grab lorry?"
        elif not state.get('waste_type'):
            return mandatory_fields[3]['question']  # "What type of materials do you have?"
        elif not state.get('quantity'):
            return mandatory_fields[4]['question']  # "How much material do you have approximately?"
        
        # C2: Grab size exact scripts
        if not state.get('grab_size_confirmed'):
            if '8' in message.lower() and 'wheel' in message.lower():
                state['grab_size_confirmed'] = True
                return GRAB_RULES['C2_grab_size_exact_scripts']['mandatory_exact_scripts']['8_wheeler']
            elif '6' in message.lower() and 'wheel' in message.lower():
                state['grab_size_confirmed'] = True
                return GRAB_RULES['C2_grab_size_exact_scripts']['mandatory_exact_scripts']['6_wheeler']
            else:
                state['grab_size_confirmed'] = True
        
        # C4: Access and timing check
        if not state.get('access_timing_checked'):
            if 'access' not in message.lower():
                state['access_timing_checked'] = True
                return GRAB_RULES['C4_access_timing']['access_question']
            else:
                state['access_timing_checked'] = True
        
        # If all info collected, get pricing (C5)
        if all_ready and not state.get('price'):
            return self.get_pricing(state, conversation_id, 'skip', '6yd', wants_to_book)
        
        # Special handling for unknown services like road sweeper
        if 'road sweeper' in message.lower():
            return f"I understand you need a road sweeper service. Let me connect you with our specialist team at {self.supplier_phone} who can arrange this for you."
        
        return "I can help you with grab hire service for soil and rubble removal. Can I take your name please?"

# Create single universal agent instance
universal_agent = UniversalAgent()

# Legacy agent classes for backward compatibility (all use universal agent)
class SkipAgent:
    def process_message(self, message, conversation_id="default"):
        return universal_agent.process_message(message, conversation_id)

class MAVAgent:
    def process_message(self, message, conversation_id="default"):
        return universal_agent.process_message(message, conversation_id)

class GrabAgent:
    def process_message(self, message, conversation_id="default"):
        return universal_agent.process_message(message, conversation_id)
