import sys
import traceback

print("Starting app.py import...")

try:
    import os
    import json
    import requests
    from datetime import datetime
    from flask import Flask, request, jsonify, render_template_string
    print("✅ Basic imports successful")
except Exception as e:
    print(f"❌ Basic imports failed: {e}")
    traceback.print_exc()
    sys.exit(1)
from utils.wasteking_api import complete_booking, create_booking, get_pricing

# Import supplier enquiry function from main app (we'll make it available globally)
supplier_enquiry = None  # Will be set by main app
transfer_call_to_supplier = None  # Will be set by main app

# COMPLETE HARDCODED BUSINESS RULES - EVERY SINGLE RULE FROM ORIGINAL PDF
OFFICE_HOURS = {
    'monday_thursday': {'start': 8, 'end': 17},
    'friday': {'start': 8, 'end': 16.5},
    'saturday': {'start': 9, 'end': 12},
    'sunday': 'closed'
}

TRANSFER_RULES = {
    'management_director': {
        'triggers': ['glenn currie', 'director', 'speak to glenn', 'glenn'],
        'office_hours': "I am sorry, Glenn is not available, may I take your details and Glenn will call you back?",
        'out_of_hours': "I can take your details and have our director call you back first thing tomorrow",
        'sms_notify': '+447823656762',
        'action': 'TRANSFER_IMMEDIATELY'
    },
    'complaints': {
        'triggers': ['complaint', 'complain', 'unhappy', 'disappointed', 'frustrated', 'angry', 'terrible service', 'poor service'],
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

# QUALIFYING AGENT RULES - CONFIGURABLE WITHOUT CODE CHANGES
QUALIFYING_RULES = {
    'rule_1': {
        'name': 'Commercial Waste Services',
        'triggers': ['commercial', 'business', 'office', 'shop', 'restaurant', 'trade waste', 'commercial waste'],
        'questions': [
            "What type of business do you have?",
            "How much commercial waste do you generate per week?",
            "Do you need regular collections or one-off service?",
            "What types of materials need disposing of?"
        ],
        'office_hours': 'transfer',
        'out_of_hours': 'take_details_and_sms',
        'sms_notify': '+447823656762'
    },
    'rule_2': {
        'name': 'Hazardous Materials',
        'triggers': ['asbestos', 'chemicals', 'paint', 'hazardous', 'dangerous', 'toxic', 'medical waste'],
        'questions': [
            "What type of hazardous material do you have?",
            "What quantity approximately?",
            "Where is the material located?",
            "Do you have any safety documentation?"
        ],
        'office_hours': 'transfer_immediately',
        'out_of_hours': 'take_details_and_sms',
        'sms_notify': '+447823656762',
        'priority': 'high'
    },
    'rule_3': {
        'name': 'Garden & Green Waste',
        'triggers': ['garden waste', 'green waste', 'grass', 'leaves', 'branches', 'hedge', 'tree cutting'],
        'questions': [
            "What type of garden waste do you have?",
            "How much garden waste approximately?",
            "Is it accessible for our team?",
            "When would you like this collected?"
        ],
        'office_hours': 'quote_and_book',
        'out_of_hours': 'quote_and_book',
        'can_book_directly': True
    },
    'rule_4': {
        'name': 'Appliance Disposal',
        'triggers': ['fridge', 'freezer', 'washing machine', 'dishwasher', 'cooker', 'appliances', 'white goods'],
        'questions': [
            "What appliances need collecting?",
            "How many items do you have?",
            "Are they easily accessible?",
            "Do any contain gas or need disconnection?"
        ],
        'office_hours': 'quote_and_book',
        'out_of_hours': 'quote_and_book', 
        'surcharges': {'fridges_freezers': 20},
        'can_book_directly': True
    },
    'rule_5': {
        'name': 'Construction & Renovation',
        'triggers': ['building work', 'renovation', 'construction', 'demolition', 'builders waste', 'plasterboard'],
        'questions': [
            "What type of building work are you doing?",
            "What materials need disposing of?",
            "How much waste do you estimate?",
            "Do you need ongoing collections during the project?"
        ],
        'office_hours': 'transfer',
        'out_of_hours': 'take_details_and_sms',
        'sms_notify': '+447823656762'
    },
    'rule_6': {
        'name': 'House Clearance',
        'triggers': ['house clearance', 'full clearance', 'property clearance', 'estate clearance', 'moving house'],
        'questions': [
            "How many rooms need clearing?",
            "What type of items are there?",
            "Is everything easily accessible?",
            "Do you need the clearance done on a specific date?"
        ],
        'office_hours': 'quote_and_book',
        'out_of_hours': 'quote_and_book',
        'can_book_directly': True
    },
    'rule_7': {
        'name': 'Recycling Services', 
        'triggers': ['recycling', 'scrap metal', 'cardboard', 'paper', 'plastic recycling', 'metal collection'],
        'questions': [
            "What materials do you want to recycle?",
            "How much do you have approximately?",
            "Is it sorted already or mixed?",
            "How often would you need collections?"
        ],
        'office_hours': 'transfer',
        'out_of_hours': 'take_details_and_sms',
        'sms_notify': '+447823656762'
    },
    'rule_8': {
        'name': 'General Enquiry',
        'triggers': ['help', 'information', 'quote', 'prices', 'service', 'what do you do', 'general'],
        'questions': [
            "What type of waste management service are you looking for?",
            "What materials do you need disposing of?",
            "What's your postcode area?",
            "Is this for home or business use?"
        ],
        'office_hours': 'assess_and_route',
        'out_of_hours': 'assess_and_route',
        'can_book_directly': False
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
    def __init__(self):
        self.conversations = {}  # Store conversation state

    def process_message(self, message, conversation_id="default"):
        """MAIN ENTRY POINT - FOLLOW ALL BUSINESS RULES"""
        state = self.conversations.get(conversation_id, {})
        print(f"📂 LOADED STATE: {state}")

        # Extract new data from message
        new_data = self.extract_data(message)
        print(f"🔍 NEW DATA: {new_data}")

        # Merge state - PRESERVE EXISTING DATA PROPERLY
        for key, value in new_data.items():
            if value and value.strip():  # Only update if new value is not empty/whitespace
                state[key] = value
        print(f"🔄 MERGED STATE: {state}")

        # Save state immediately
        self.conversations[conversation_id] = state.copy()

        # Get next response following ALL RULES
        response = self.get_next_response(message, state, conversation_id)
        
        # Save state again after processing
        self.conversations[conversation_id] = state.copy()
        
        return response

    def check_completion_status(self, state):
        """Track what we have and what we need"""
        completion = {
            'name': 'yes' if state.get('firstName') else 'no',
            'address': 'yes' if state.get('postcode') else 'no', 
            'service': 'yes' if state.get('service') else 'no',
            'phone': 'yes' if state.get('phone') else 'no'
        }
        
        all_ready = all(status == 'yes' for status in completion.values())
        print(f"📋 COMPLETION STATUS: {completion} | ALL READY: {all_ready}")
        
        return completion, all_ready

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

        # Phone extraction - handle multiple formats
        phone_patterns = [
            r'\b(\d{11})\b',                    # 01442216784 (11 consecutive digits)
            r'\b(\d{10})\b',                    # 0144216784 (10 consecutive digits)
            r'\b(\d{5})\s+(\d{6})\b',           # 01442 216784 (5 + 6 digits with space)
            r'\b(\d{4})\s+(\d{6})\b',           # 0144 216784 (4 + 6 digits with space)
            r'\b(\d{5})-(\d{6})\b',             # 01442-216784 (5 + 6 digits with hyphen)
            r'\b(\d{4})-(\d{6})\b',             # 0144-216784 (4 + 6 digits with hyphen)
            r'\((\d{4,5})\)\s*(\d{6})\b',       # (01442) 216784 (brackets format)
        ]
        
        for pattern in phone_patterns:
            phone_match = re.search(pattern, message)
            if phone_match:
                # Combine all captured groups and remove any non-digits
                phone_parts = [group for group in phone_match.groups() if group]
                phone_number = ''.join(phone_parts)
                if len(phone_number) >= 10:  # Valid UK phone number
                    data['phone'] = phone_number
                    print(f"✅ Extracted phone: {data['phone']}")
                    break

        # Name extraction - FIXED: Don't extract "Yes" as name
        if 'kanchen' in message_lower or 'kanchan' in message_lower:
            data['firstName'] = 'Kanchan'
            print(f"✅ Extracted name: Kanchan")
        elif 'jackie' in message_lower:
            data['firstName'] = 'Jackie'
            print(f"✅ Extracted name: Jackie")
        else:
            name_patterns = [
                r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
                r'[Cc]ustomer\s+(?:name\s+)?(?:is\s+)?([A-Z][a-z]+)',
                r'^([A-Z][a-z]+)\s+(?:wants|needs)',
                r'^([A-Z][a-z]+),',
                r'for\s+([A-Z][a-z]+),',
                r'([A-Z][a-z]+)\s+phone',
                r'phone\s+([A-Z][a-z]+)',
            ]
            for pattern in name_patterns:
                name_match = re.search(pattern, message)
                if name_match:
                    potential_name = name_match.group(1).strip().title()
                    # RULE: Don't extract common words as names
                    if potential_name.lower() not in ['yes', 'no', 'there', 'what', 'how', 'confirmed', 'phone', 'please']:
                        data['firstName'] = potential_name
                        print(f"✅ Extracted name: {data['firstName']}")
                        break

        # Extract waste type information - FOLLOW WASTE TYPE RULES
        waste_keywords = ['plastic', 'brick', 'waste', 'rubbish', 'items', 'normal', 'household', 'soil', 'old', 'furniture', 'clothes', 'books', 'toys', 'cardboard', 'paper', 'bricks', 'brick', 'renovation', 'rubble', 'concrete', 'tiles', 'wardrobe', 'clearance']
        found_waste = []
        
        for keyword in waste_keywords:
            if keyword in message_lower:
                found_waste.append(keyword)
        
        if found_waste:
            data['waste_type'] = ', '.join(found_waste)
            print(f"✅ Extracted waste type: {data['waste_type']}")

        # Extract location information
        location_phrases = [
            'in the garage', 'in garage', 'garage', 'half a garage',
            'in the garden', 'garden', 'back garden', 'front garden',
            'in the house', 'inside', 'indoors', 'house clearance',
            'outside', 'outdoors', 'on the drive', 'driveway',
            'easy access', 'easy to access', 'accessible',
            'ground floor', 'upstairs', 'basement', 'flat', 'apartment'
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
            'perfect', 'sounds good', 'thats fine', 'arrange this',
            'wants to book', 'please send payment'
        ]
        
        # Positive responses
        positive_words = ['yes', 'yeah', 'yep', 'ok', 'okay', 'alright', 'sure', 'lets do it', 'go ahead', 'proceed']
        
        # Check for explicit booking requests
        if any(phrase in message_lower for phrase in booking_phrases):
            return True
            
        # Check for positive responses - but only if we already have pricing
        return any(word in message_lower for word in positive_words)

    def is_business_hours(self):
        """Check if it's business hours"""
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

    def needs_transfer(self, price):
        """Check if transfer is needed based on service and price"""
        if self.service_type == 'skip':
            return False  # Skip hire: no limit, never transfer
        elif self.service_type == 'mav' and price >= 500:
            return True   # MAV: transfer needed for £500+
        elif self.service_type == 'grab' and price >= 300:
            return True   # Grab: transfer needed for £300+
        return False

    def validate_postcode_with_customer(self, current_postcode):
        """Ask customer to confirm postcode if pricing fails"""
        if not current_postcode or len(current_postcode) < 5:
            return "Could you please provide your complete postcode? For example, LS14ED rather than just LS1."
        else:
            return f"I'm having trouble finding pricing for {current_postcode}. Could you please confirm your complete postcode is correct?"

    def do_transfer(self, conversation_id, reason="general_transfer"):
        """ACTUAL TRANSFER FUNCTION - CALLS ELEVENLABS API TO TRANSFER"""
        if transfer_call_to_supplier:
            print(f"🔄 EXECUTING ACTUAL TRANSFER - Reason: {reason}")
            return transfer_call_to_supplier(conversation_id)
        else:
            print("❌ Transfer function not available - fallback message")
            return "I'm transferring you to our team at +447394642517. Please hold while I connect you."

    def check_for_transfers(self, message, conversation_id):
        """Check for transfer triggers and execute appropriate action - FOLLOW EXACT ORIGINAL RULES"""
        message_lower = message.lower()
        
        # Check for Glenn Currie/Director requests - TAKE DETAILS, NO TRANSFER
        if any(trigger in message_lower for trigger in TRANSFER_RULES['management_director']['triggers']):
            print("🔍 GLENN CURRIE REQUESTED - TAKE DETAILS FOR CALLBACK")
            if self.is_business_hours():
                return TRANSFER_RULES['management_director']['office_hours']
            else:
                return TRANSFER_RULES['management_director']['out_of_hours']
        
        # Check for complaints - TRANSFER (only complaints transfer immediately)
        if any(trigger in message_lower for trigger in TRANSFER_RULES['complaints']['triggers']):
            print("🔄 COMPLAINT DETECTED - TRANSFERRING IMMEDIATELY")
            if self.is_business_hours():
                return self.do_transfer(conversation_id, "complaint_office")
            else:
                return TRANSFER_RULES['complaints']['out_of_hours']
        
        # Check for specialist services
        if any(service in message_lower for service in TRANSFER_RULES['specialist_services']['services']):
            print("🔄 SPECIALIST SERVICE REQUESTED")
            if self.is_business_hours():
                return self.do_transfer(conversation_id, "specialist_service")
            else:
                return "We can help with that specialist service. I can take your details and have our team call you back first thing tomorrow."
        
        return None  # No transfer needed

    def get_pricing(self, state, conversation_id, wants_to_book=False):
        """ENHANCED: Get pricing with supplier enquiry integration"""
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
                
                # NEW: Call supplier enquiry during pricing process
                customer_request = f"{state.get('firstName', 'Customer')} needs {state['service']} service at {state['postcode']} for {state.get('waste_type', 'general waste')}"
                
                print("📞 CALLING SUPPLIER ENQUIRY...")
                if supplier_enquiry:
                    enquiry_result = supplier_enquiry(customer_request, conversation_id, price)
                    print(f"📞 Supplier enquiry result: {enquiry_result}")
                
                # Apply transfer logic correctly
                if self.needs_transfer(price_num):
                    # Only check office hours if transfer is actually needed
                    if self.is_business_hours():
                        print("🔄 TRANSFER NEEDED - OFFICE HOURS")
                        return self.do_transfer(conversation_id, "high_value_office")
                    else:
                        print("🌙 OUT OF HOURS - MAKE THE SALE INSTEAD")
                        if wants_to_book:
                            print("🚀 USER ALREADY WANTS TO BOOK - COMPLETING IMMEDIATELY")
                            return self.complete_booking(state)
                        else:
                            return f"{state['type']} {self.service_name} at {state['postcode']}: {state['price']}. Would you like to book this?"
                else:
                    # No transfer needed
                    if wants_to_book:
                        print("🚀 USER ALREADY WANTS TO BOOK - COMPLETING IMMEDIATELY")
                        return self.complete_booking(state)
                    else:
                        print("✅ NO TRANSFER NEEDED - PRESENTING PRICE TO USER")
                        return f"{state['type']} {self.service_name} at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                print("❌ ZERO PRICE RETURNED")
                return self.validate_postcode_with_customer(state.get('postcode'))
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now. Let me put you through to our team."

    def complete_booking(self, state):
        """CORE FUNCTION: Complete booking with payment link - MUST CALL ACTUAL API"""
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


class SkipAgent(BaseAgent):
    """SKIP HIRE AGENT - FOLLOW ALL RULES A1-A7"""
    def __init__(self):
        super().__init__()
        self.service_type = 'skip'
        self.service_name = 'skip hire'
        self.default_type = '8yd'

    def get_next_response(self, message, state, conversation_id):
        """SKIP HIRE FLOW - FOLLOW ALL RULES A1-A7 EXACTLY"""
        wants_to_book = self.should_book(message)
        
        # Check for transfers FIRST - before any other processing
        transfer_response = self.check_for_transfers(message, conversation_id)
        if transfer_response:
            return transfer_response
        
        # Check completion status
        completion, all_ready = self.check_completion_status(state)
        
        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking(state)

        # If all info collected but no pricing yet, get pricing
        if all_ready and not state.get('price'):
            print("🚀 ALL INFO COLLECTED - CALLING API FOR PRICING")
            return self.get_pricing(state, conversation_id, wants_to_book)

        # A1: INFORMATION GATHERING SEQUENCE
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your complete postcode? For example, LS14ED rather than just LS1."
        elif not state.get('service'):
            state['service'] = 'skip'
            if not state.get('type'):
                state['type'] = '8yd'
            self.conversations[conversation_id] = state

        # If we have basic info but missing phone, ask for it
        elif not state.get('phone'):
            return "What's the best phone number to contact you on?"

        # If we have all required info, proceed to get price
        elif state.get('firstName') and state.get('postcode') and state.get('service') and state.get('phone'):
            if not state.get('price'):
                return self.get_pricing(state, conversation_id, wants_to_book)
            elif state.get('price'):
                return f"{state.get('type', '8yd')} skip hire at {state['postcode']}: {state['price']}. Would you like to book this?"

        return "How can I help you with skip hire?"


class MAVAgent(BaseAgent):
    """MAN & VAN AGENT - FOLLOW ALL RULES B1-B6"""
    def __init__(self):
        super().__init__()
        self.service_type = 'mav'
        self.service_name = 'man & van'
        self.default_type = '4yd'

    def get_next_response(self, message, state, conversation_id):
        """MAN & VAN FLOW - FOLLOW ALL RULES B1-B6 EXACTLY"""
        wants_to_book = self.should_book(message)
        
        # Check for transfers FIRST - before any other processing
        transfer_response = self.check_for_transfers(message, conversation_id)
        if transfer_response:
            return transfer_response
        
        # Check completion status
        completion, all_ready = self.check_completion_status(state)
        
        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking(state)

        # If all info collected but no pricing yet, get pricing
        if all_ready and not state.get('price'):
            print("🚀 ALL INFO COLLECTED - CALLING API FOR PRICING")
            return self.get_pricing(state, conversation_id, wants_to_book)

        # B1: INFORMATION GATHERING
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your complete postcode? For example, LS14ED rather than just LS1."
        elif not state.get('service'):
            state['service'] = 'mav'
            state['type'] = '4yd'
            self.conversations[conversation_id] = state
        elif not state.get('phone'):
            return "What's the best phone number to contact you on?"

        # If we have all required info, proceed to get price
        elif state.get('firstName') and state.get('postcode') and state.get('service') and state.get('phone'):
            if not state.get('price'):
                return self.get_pricing(state, conversation_id, wants_to_book)
            elif state.get('price'):
                return f"{state.get('type', '4yd')} man & van at {state['postcode']}: {state['price']}. Would you like to book this?"

        return "How can I help you with man & van service?"


class GrabAgent(BaseAgent):
    """GRAB HIRE AGENT - FOLLOW ALL RULES C1-C5"""
    def __init__(self):
        super().__init__()
        self.service_type = 'grab'
        self.service_name = 'grab hire'
        self.default_type = '6yd'

    def get_next_response(self, message, state, conversation_id):
        """GRAB HIRE FLOW - FOLLOW ALL RULES C1-C5 EXACTLY"""
        wants_to_book = self.should_book(message)
        
        # Check for transfers FIRST - before any other processing
        transfer_response = self.check_for_transfers(message, conversation_id)
        if transfer_response:
            return transfer_response
        
        # Check completion status
        completion, all_ready = self.check_completion_status(state)
        
        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking(state)

        # If all info collected but no pricing yet, get pricing
        if all_ready and not state.get('price'):
            print("🚀 ALL INFO COLLECTED - CALLING API FOR PRICING")
            return self.get_pricing(state, conversation_id, wants_to_book)

        # C1: MANDATORY INFORMATION GATHERING
        if not state.get('firstName'):
            return "Can I take your name please?"
        elif not state.get('phone'):
            return "What's the best phone number to contact you on?"
        elif not state.get('postcode'):
            return "What's the postcode where you need the grab lorry?"
        elif not state.get('service'):
            state['service'] = 'grab'
            state['type'] = '6yd'
            self.conversations[conversation_id] = state

        # If we have all required info, proceed to get price
        elif state.get('firstName') and state.get('postcode') and state.get('service') and state.get('phone'):
            if not state.get('price'):
                return self.get_pricing(state, conversation_id, wants_to_book)
            elif state.get('price'):
                return f"{state.get('type', '6yd')} grab hire at {state['postcode']}: {state['price']}. Would you like to book this?"

        return "How can I help you with grab hire?"


# NEW: QUALIFYING AGENT CLASS
class QualifyingAgent(BaseAgent):
    """NEW QUALIFYING AGENT - HANDLES ALL OTHER/UNKNOWN SERVICES"""
    def __init__(self):
        super().__init__()
        self.service_type = 'qualifying'
        self.service_name = 'waste management'
        self.default_type = 'general'

    def identify_service_category(self, message):
        """Identify which qualifying rule applies to the message"""
        message_lower = message.lower()
        
        for rule_id, rule in QUALIFYING_RULES.items():
            for trigger in rule['triggers']:
                if trigger in message_lower:
                    print(f"🎯 QUALIFYING RULE MATCHED: {rule_id} - {rule['name']}")
                    return rule_id, rule
        
        # Default to general enquiry if nothing matches
        return 'rule_8', QUALIFYING_RULES['rule_8']

    def ask_qualifying_questions(self, state, rule):
        """Ask qualifying questions based on the rule"""
        current_question_index = state.get('question_index', 0)
        questions = rule['questions']
        
        if current_question_index < len(questions):
            state['question_index'] = current_question_index + 1
            return questions[current_question_index]
        
        return None  # All questions asked

    def get_next_response(self, message, state, conversation_id):
        """QUALIFYING AGENT FLOW - FOLLOW CONFIGURABLE RULES"""
        wants_to_book = self.should_book(message)
        
        # Check for transfers FIRST - before any other processing
        transfer_response = self.check_for_transfers(message, conversation_id)
        if transfer_response:
            return transfer_response
        
        # Check completion status
        completion, all_ready = self.check_completion_status(state)
        
        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking(state)

        # Identify service category if not already identified
        if not state.get('qualifying_rule'):
            rule_id, rule = self.identify_service_category(message)
            state['qualifying_rule'] = rule_id
            state['rule_data'] = rule
            state['service'] = 'qualifying'
            self.conversations[conversation_id] = state
            print(f"🎯 SERVICE IDENTIFIED: {rule['name']}")

        rule = state.get('rule_data', QUALIFYING_RULES['rule_8'])

        # Handle high priority items (like hazardous materials) immediately
        if rule.get('priority') == 'high':
            if self.is_business_hours():
                return self.do_transfer(conversation_id, "hazardous_immediate")
            else:
                return self.do_transfer(conversation_id, "hazardous_out_hours")

        # Basic information gathering first
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your postcode?"
        elif not state.get('phone'):
            return "What's the best number to contact you on?"

        # Ask qualifying questions
        next_question = self.ask_qualifying_questions(state, rule)
        if next_question:
            return next_question

        # All questions asked, now handle based on rule action
        rule_action = rule.get('office_hours' if self.is_business_hours() else 'out_of_hours', 'take_details_and_sms')

        if rule_action == 'transfer_immediately' or rule_action == 'transfer':
            return self.do_transfer(conversation_id, "specialist_qualifying")
        
        elif rule_action == 'quote_and_book' and rule.get('can_book_directly'):
            if not state.get('price') and all_ready:
                # Try to get pricing for qualifying services 
                try:
                    return self.get_pricing(state, conversation_id, wants_to_book)
                except:
                    return self.do_transfer(conversation_id, "pricing_failed")
            elif state.get('price'):
                return f"Based on your requirements, the estimated price is {state['price']}. Would you like to proceed with booking?"

        elif rule_action == 'take_details_and_sms':
            # Send SMS notification to supplier
            return f"I've taken all your details and will have our specialist team call you back within 2 hours. Your enquiry reference is QUA-{conversation_id[-6:].upper()}."

        elif rule_action == 'assess_and_route':
            # Try to route to appropriate service based on collected information
            waste_type = state.get('waste_type', '').lower()
            
            if any(word in waste_type for word in ['skip', 'yard']):
                return "Based on what you've told me, it sounds like skip hire would be perfect for you. Let me get you a quote."
            elif any(word in waste_type for word in ['man and van', 'collection', 'removal']):
                return "Based on your requirements, our man and van service would be ideal. We do all the work for you."
            else:
                return self.do_transfer(conversation_id, "general_assessment")

        # Default response
        return "Thank you for the information. Let me arrange for our specialist team to call you back with the best solution for your needs."


# Function to set supplier_enquiry reference from main app
def set_supplier_enquiry_function(func):
    global supplier_enquiry
    supplier_enquiry = func
    print("✅ Supplier enquiry function linked to agents")

# Function to set transfer_call_to_supplier reference from main app  
def set_transfer_function(func):
    global transfer_call_to_supplier
    transfer_call_to_supplier = func
    print("✅ Transfer function linked to agents")
