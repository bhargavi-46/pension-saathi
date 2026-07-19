"""Onboarding agent — Saathi's warm 5-question intake conversation.

A small state machine keyed on `widow.onboarding_step` (0..5).  Each turn:
parse the user's answer for the current question, store it, ask the next one.
Replies in Hindi when the user writes Devanagari, English otherwise.

Answer parsing is deterministic (regex/keyword) with a Gemini assist when a
real API key is configured — the deterministic path keeps the demo reliable.
"""

import json
import re

from db import Conversation, SessionLocal, Widow, log_action
from services.gemini import gemini_service

INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry",
    "Chandigarh", "Andaman and Nicobar", "Lakshadweep",
]

LOCAL_STATE_NAMES = {
    # Hindi
    "बिहार": "Bihar", "उत्तर प्रदेश": "Uttar Pradesh", "मध्य प्रदेश": "Madhya Pradesh",
    "राजस्थान": "Rajasthan", "महाराष्ट्र": "Maharashtra", "कर्नाटक": "Karnataka",
    "झारखंड": "Jharkhand", "पश्चिम बंगाल": "West Bengal", "दिल्ली": "Delhi",
    "पंजाब": "Punjab", "हरियाणा": "Haryana", "गुजरात": "Gujarat", "ओडिशा": "Odisha",
    "तेलंगाना": "Telangana", "आंध्र प्रदेश": "Andhra Pradesh",
    # Telugu
    "తెలంగాణ": "Telangana", "ఆంధ్రప్రదేశ్": "Andhra Pradesh", "ఆంధ్ర ప్రదేశ్": "Andhra Pradesh",
    "బీహార్": "Bihar", "కర్ణాటక": "Karnataka", "మహారాష్ట్ర": "Maharashtra",
    "తమిళనాడు": "Tamil Nadu", "ఒడిశా": "Odisha",
}

OCCUPATIONS = {
    "farmer": ["farmer", "farming", "kisan", "किसान", "खेती", "రైతు", "వ్యవసాయం"],
    "laborer": ["laborer", "labourer", "labour", "mazdoor", "मजदूर", "मज़दूर", "daily wage",
                "కూలీ", "కూలి", "construction", "निर्माण"],
    "government job": ["government", "sarkari", "सरकारी", "ప్రభుత్వ", "గవర్నమెంట్"],
    "private job": ["private", "company", "प्राइवेट", "कंपनी", "ప్రైవేట్", "కంపెనీ"],
    "driver": ["driver", "ड्राइवर", "డ్రైవర్"],
    "shopkeeper": ["shop", "दुकान", "దుకాణం"],
}

QUESTIONS = {
    "hi": [
        "नमस्ते बहन। मैं साथी हूँ — मैं आपको हर वह सरकारी योजना दिलाने में मदद करूँगी जिसकी आप हकदार हैं। सबसे पहले, आपका नाम क्या है?",
        "धन्यवाद {name} जी। आप किस राज्य और ज़िले में रहती हैं?",
        "आपकी उम्र कितनी है, और आपके कितने बच्चे हैं?",
        "आपके पति का काम क्या था? (किसान, मजदूर, सरकारी नौकरी, प्राइवेट नौकरी...)",
        "अभी आपकी महीने की कमाई लगभग कितनी है?",
    ],
    "en": [
        "Hello sister. I am Saathi — I will help you claim every government scheme you are entitled to. First, what is your name?",
        "Thank you, {name}. Which state and district do you live in?",
        "How old are you, and how many children do you have?",
        "What was your husband's occupation? (farmer, laborer, government job, private job...)",
        "What is your rough monthly income right now?",
    ],
    "te": [
        "నమస్తే అక్కా. నేను సాథి — మీకు రావాల్సిన ప్రతి ప్రభుత్వ పథకాన్ని పొందడంలో సహాయం చేస్తాను. ముందుగా, మీ పేరు ఏమిటి?",
        "ధన్యవాదాలు {name} గారు. మీరు ఏ రాష్ట్రం, ఏ జిల్లాలో ఉంటున్నారు?",
        "మీ వయస్సు ఎంత, మీకు ఎంతమంది పిల్లలు?",
        "మీ భర్త ఏమి పని చేసేవారు? (రైతు, కూలీ, ప్రభుత్వ ఉద్యోగం, ప్రైవేట్ ఉద్యోగం...)",
        "ప్రస్తుతం మీ నెల ఆదాయం సుమారుగా ఎంత?",
    ],
}

DONE_MESSAGE = {
    "hi": "धन्यवाद {name} जी। अब मैं आपके लिए हर योजना खोजूँगी जिसकी आप हकदार हैं। कृपया अपने पति का मृत्यु प्रमाण पत्र (death certificate) की फोटो भेजें — 📎 बटन दबाकर।",
    "en": "Thank you, {name}. I will now search for every scheme you are entitled to. Please also send a photo of your husband's death certificate using the 📎 button.",
    "te": "ధన్యవాదాలు {name} గారు. ఇప్పుడు మీకు రావాల్సిన ప్రతి పథకాన్ని వెతుకుతాను. దయచేసి మీ భర్త మరణ ధృవీకరణ పత్రం (death certificate) ఫోటోను 📎 బటన్ ద్వారా పంపండి.",
}

LANG_CODES = {"hi": "hi-IN", "te": "te-IN", "en": "en-IN"}

# ---- Information-gap follow-up (interactive verification loop) ------------
# When discovery matches a scheme that hinges on a household fact the intake
# never asked (Sukanya Samriddhi Yojana needs a daughter under 10), the
# pipeline HALTS and the voice agent asks this question. Her answer is stored
# on the profile and discovery resumes.
DAUGHTER_QUESTION = {
    "hi": "{name} जी, आपने बताया कि आपके {n} बच्चे हैं। क्या उनमें कोई बेटी है जिसकी उम्र 10 साल से कम है? अगर हाँ, तो वह सुकन्या समृद्धि योजना (Sukanya Samriddhi Yojana) की हकदार होगी। कृपया हाँ या नहीं बताएं।",
    "te": "{name} గారు, మీకు {n} పిల్లలు అని చెప్పారు కదా. వారిలో 10 సంవత్సరాల కంటే తక్కువ వయస్సు ఉన్న ఆడపిల్ల ఉందా? ఉంటే, ఆమె సుకన్య సమృద్ధి యోజన (Sukanya Samriddhi Yojana) పథకానికి అర్హురాలు అవుతుంది. దయచేసి అవును లేదా లేదు అని చెప్పండి.",
    "en": "{name} sister, you said you have {n} children. Is one of them a daughter under 10 years old? If yes, she qualifies for the Sukanya Samriddhi Yojana savings scheme. Please reply yes or no.",
}

DAUGHTER_YES_REPLY = {
    "hi": "बहुत अच्छा! आपकी बेटी के लिए सुकन्या समृद्धि योजना जोड़ रही हूँ। अब बाकी योजनाओं के साथ आगे बढ़ती हूँ…",
    "te": "చాలా మంచిది! మీ కూతురి కోసం సుకన్య సమృద్ధి యోజనను చేరుస్తున్నాను. ఇప్పుడు మిగతా పథకాలతో ముందుకు వెళ్తున్నాను…",
    "en": "Wonderful! I'm adding Sukanya Samriddhi Yojana for your daughter. Continuing with the other schemes now…",
}

DAUGHTER_NO_REPLY = {
    "hi": "समझ गई। वह योजना लागू नहीं होगी — बाकी योजनाओं के साथ आगे बढ़ती हूँ…",
    "te": "అర్థమైంది. ఆ పథకం వర్తించదు — మిగతా పథకాలతో ముందుకు వెళ్తున్నాను…",
    "en": "Understood. That scheme won't apply — continuing with the other schemes now…",
}

DAUGHTER_REASK = {
    "hi": "कृपया सिर्फ़ बताएं — क्या आपकी कोई बेटी 10 साल से छोटी है? (हाँ / नहीं)",
    "te": "దయచేసి చెప్పండి — మీకు 10 ఏళ్ల లోపు ఆడపిల్ల ఉందా? (అవును / లేదు)",
    "en": "Please just tell me — do you have a daughter under 10 years old? (yes / no)",
}

# Fallback address when the name is missing ("Sister" instead of a blank).
GAP_FALLBACK_NAME = {"hi": "बहन", "te": "అక్కా", "en": "Sister"}

# ---- Answer validation (one gentle re-ask, then accept) --------------------
# Garbage like "kjkn, kjn" used to be stored as a state and flow straight into
# discovery. Now steps with a verifiable answer (state, age, income) re-ask
# once when nothing parseable was found; a second unparseable answer is
# accepted as-is so nobody gets stuck in a loop.
REASK = {
    1: {
        "hi": "माफ़ कीजिए, मैं वह राज्य पहचान नहीं पाई। कृपया अपना राज्य बताएं — जैसे बिहार, उत्तर प्रदेश, तेलंगाना…",
        "en": "Sorry, I couldn't recognise that state. Please tell me your state — for example Bihar, Uttar Pradesh, Telangana…",
        "te": "క్షమించండి, ఆ రాష్ట్రం నాకు అర్థం కాలేదు. దయచేసి మీ రాష్ట్రం చెప్పండి — ఉదాహరణకు తెలంగాణ, ఆంధ్రప్రదేశ్, బీహార్…",
    },
    2: {
        "hi": "कृपया अंकों में बताएं — आपकी उम्र कितनी है और कितने बच्चे हैं? (जैसे: 40 साल, 2 बच्चे)",
        "en": "Please tell me in numbers — your age and how many children you have. (For example: 40 years, 2 children)",
        "te": "దయచేసి సంఖ్యలలో చెప్పండి — మీ వయస్సు ఎంత, ఎంతమంది పిల్లలు? (ఉదా: 40 ఏళ్ళు, 2 పిల్లలు)",
    },
    4: {
        "hi": "कृपया अंकों में बताएं — महीने की कमाई लगभग कितनी है? (जैसे: 3000)",
        "en": "Please tell me a number — roughly how much do you earn per month? (For example: 3000)",
        "te": "దయచేసి సంఖ్యలో చెప్పండి — నెలకు సుమారు ఎంత సంపాదిస్తారు? (ఉదా: 3000)",
    },
}

_NO_WORDS = {"no", "nahi", "nahin", "नहीं", "नही", "లేదు", "కాదు", "ledu", "kadu", "not"}
_YES_WORDS = {"yes", "haan", "han", "ha", "हाँ", "हा", "जी", "అవును", "ఉంది", "avunu", "undi"}
_DAUGHTER_WORDS = {"daughter", "girl", "बेटी", "लड़की", "बिटिया", "ఆడపిల్ల", "అమ్మాయి",
                   "కూతురు", "beti", "ladki", "kuthuru", "ammayi"}


def parse_yes_no(message: str) -> bool | None:
    """Multilingual yes/no. Negatives win ("no daughter" → no); a daughter
    word without a negative counts as yes ("1 girl, 8 years" → yes)."""
    tokens = set(re.findall(r"[\wऀ-ॿఀ-౿]+", message.lower()))
    if tokens & _NO_WORDS:
        return False
    if tokens & (_YES_WORDS | _DAUGHTER_WORDS):
        return True
    return None


# Reply for messages AFTER onboarding is complete ("yes", "ok", questions) —
# without this the agent loops back to "send the death certificate" forever.
POST_ONBOARDING = {
    "hi": "धन्यवाद! आपकी जानकारी पूरी है। आवेदनों की स्थिति डैशबोर्ड पर देखें। अगर आधार कार्ड या बैंक पासबुक भेजना बाकी है, तो 📎 बटन से भेजें।",
    "en": "Thank you! Your details are complete. You can watch your applications' progress on the dashboard. If you still need to send your Aadhaar card or bank passbook, use the 📎 button.",
    "te": "ధన్యవాదాలు! మీ వివరాలు పూర్తయ్యాయి. దరఖాస్తుల స్థితిని డాష్‌బోర్డ్‌లో చూడండి. ఆధార్ కార్డు లేదా బ్యాంక్ పాస్‌బుక్ పంపాల్సి ఉంటే 📎 బటన్ ద్వారా పంపండి.",
}


def detect_language(text: str) -> str | None:
    """Language of THIS message. None = no letters at all (digits/emoji) —
    caller should keep the conversation's current language."""
    if re.search(r"[ఀ-౿]", text):  # Telugu script
        return "te"
    if re.search(r"[ऀ-ॿ]", text):  # Devanagari script
        return "hi"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return None


def _extract_name(message: str) -> str:
    cleaned = re.sub(
        r"(?i)(mera naam|मेरा नाम|my name is|i am|naam|नाम|hai|है|hoon|हूँ|hun"
        r"|నా పేరు|పేరు|నేను|అంటారు|\.)",
        " ",
        message,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else message.strip().title()


def _extract_state_district(message: str) -> tuple[str | None, str | None]:
    state = None
    for local, english in LOCAL_STATE_NAMES.items():
        if local in message:
            state = english
            break
    if not state:
        for s in INDIAN_STATES:
            if s.lower() in message.lower():
                state = s
                break
    # District: whatever word remains that isn't the state (best effort)
    district = None
    leftovers = re.sub(r"(?i)(state|district|ज़िला|जिला|राज्य|జిల్లా|రాష్ట్రం|,)", " ", message)
    if state:
        leftovers = re.sub(re.escape(state), " ", leftovers, flags=re.IGNORECASE)
        for local in LOCAL_STATE_NAMES:
            leftovers = leftovers.replace(local, " ")
    words = [w for w in re.findall(r"[\wऀ-ॿఀ-౿]+", leftovers) if len(w) > 2]
    if words:
        district = words[0].title()
    return state, district


def _extract_numbers(message: str) -> list[int]:
    # Convert Devanagari + Telugu digits, then pull integers
    trans = str.maketrans("०१२३४५६७८९౦౧౨౩౪౫౬౭౮౯", "01234567890123456789")
    return [int(n) for n in re.findall(r"\d+", message.translate(trans))]


def _extract_occupation(message: str) -> str:
    lowered = message.lower()
    for occupation, keywords in OCCUPATIONS.items():
        if any(k in lowered or k in message for k in keywords):
            return occupation
    return message.strip()[:60]


_LLM_EXTRACT_PROMPTS = {
    1: 'Extract as JSON: {"state": <Indian state name in English or null>, "district": <district transliterated to English or null>}',
    2: 'Extract as JSON: {"age": <the woman\'s age as number or null>, "children_count": <HOW MANY children (a count, not their ages) or null>}',
    4: 'Extract as JSON: {"monthly_income": <monthly income in rupees as a number, converting number-words in any Indian language, or null>}',
}


def _llm_extract(step: int, message: str) -> dict | None:
    """Gemini fallback when regex/keyword parsing fails — handles number-words
    ("నాలుగు వేల ఐదు వందలు" = 4500), unusual phrasing, any Indian language."""
    if gemini_service.mock or step not in _LLM_EXTRACT_PROMPTS:
        return None
    try:
        raw = gemini_service.chat(
            f"USER MESSAGE (may be Telugu/Hindi/English): {message}\n"
            f"{_LLM_EXTRACT_PROMPTS[step]}\nReturn ONLY the JSON object."
        )
        cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        return json.loads(cleaned)
    except Exception:
        return None


def _parse_answer(step: int, message: str, widow: Widow) -> bool:
    """Store what was understood; return False when nothing verifiable was
    found (caller may re-ask). Name and occupation are free text — always True."""
    if step == 0:
        widow.name = _extract_name(message)
    elif step == 1:
        state, district = _extract_state_district(message)
        if not state:
            llm = _llm_extract(1, message) or {}
            llm_state = (llm.get("state") or "").strip().title()
            state = llm_state if llm_state in INDIAN_STATES else None
            district = district or llm.get("district")
        widow.state = state or message.strip().title()
        widow.district = district
        return state is not None
    elif step == 2:
        age = children = None
        numbers = _extract_numbers(message)
        if numbers:
            age = numbers[0]
            if len(numbers) > 1:
                # "42, 2 children" → count 2. But "45, sons 14 and 10" lists
                # AGES, not a count — a count over 12 is implausible, so treat
                # the remaining numbers as one age each.
                children = numbers[1] if numbers[1] <= 12 else len(numbers) - 1
            else:
                children = 0
        if age is None or not 12 <= age <= 110:
            llm = _llm_extract(2, message) or {}
            age = llm.get("age") if llm.get("age") is not None else age
            children = llm.get("children_count") if llm.get("children_count") is not None else children
        widow.age = age
        widow.children_count = children
        return age is not None and 12 <= int(age) <= 110
    elif step == 3:
        widow.husband_occupation = _extract_occupation(message)
    elif step == 4:
        numbers = _extract_numbers(message)
        if numbers:
            widow.monthly_income = numbers[0]
        else:
            llm = _llm_extract(4, message) or {}
            # None (unknown) is better than a false 0 — discovery treats
            # unknown income as "verify", not as zero income.
            widow.monthly_income = llm.get("monthly_income")
        return widow.monthly_income is not None
    return True


def handle_message(widow_id: str, message: str, preferred_language: str | None = None) -> dict:
    """One conversational turn. Returns {agent_reply, done, profile?}.

    Language priority: native script in the message > the language selected
    in the app's settings (preferred_language, e.g. "te-IN") > English.
    """
    with SessionLocal() as db:
        widow = db.get(Widow, widow_id)
        if widow is None:
            widow = Widow(id=widow_id, onboarding_step=0)
            db.add(widow)

        code_to_lang = {v: k for k, v in LANG_CODES.items()}
        # Reply in the language of THIS message (English for Latin text).
        # Only letterless messages ("3200", "👍") keep the current language.
        detected = detect_language(message)
        if detected:
            widow.language = LANG_CODES[detected]
        elif widow.language not in code_to_lang:
            widow.language = preferred_language if preferred_language in code_to_lang else "en-IN"
        lang = code_to_lang.get(widow.language, "en")
        step = widow.onboarding_step

        db.add(Conversation(widow_id=widow_id, role="user", content=message))

        # Interactive verification loop: discovery halted on an information
        # gap and asked a clarifying question — this message is her answer.
        # Store the fact, clear the gap, and tell the caller to resume
        # discovery with the completed profile.
        if widow.pending_question == "daughter_under_10":
            answer = parse_yes_no(message)
            if answer is None:
                reply = DAUGHTER_REASK[lang]
                db.add(Conversation(widow_id=widow_id, role="agent", content=reply))
                db.commit()
                return {"agent_reply": reply, "done": False, "profile": None}
            widow.has_daughter_under_10 = 1 if answer else 0
            widow.pending_question = None
            reply = (DAUGHTER_YES_REPLY if answer else DAUGHTER_NO_REPLY)[lang]
            db.add(Conversation(widow_id=widow_id, role="agent", content=reply))
            db.commit()
            log_action(
                widow_id, "voice",
                "Information gap resolved: daughter under 10 = "
                + ("YES ✓" if answer else "no")
                + " — resuming the discovery pipeline",
                {"gap": "daughter_under_10", "answer": bool(answer)},
            )
            return {"agent_reply": reply, "done": False, "resume_discovery": True, "profile": None}

        # Onboarding already finished: acknowledge instead of looping the
        # "done" message (which would also re-trigger discovery client-side).
        if step >= 5:
            reply = POST_ONBOARDING[lang]
            db.add(Conversation(widow_id=widow_id, role="agent", content=reply))
            db.commit()
            return {"agent_reply": reply, "done": False, "profile": None}

        greeting_only = step == 0 and not widow.name and re.fullmatch(
            r"(?i)\s*(hi|hello|hey|namaste|नमस्ते|नमस्कार|నమస్తే|నమస్కారం|start|शुरू)\s*[.!]*\s*",
            message,
        )

        done = False
        if greeting_only:
            reply = QUESTIONS[lang][0]
        else:
            valid = _parse_answer(step, message, widow)
            retry_key = f"retry_{step}"
            if not valid and step in REASK and widow.pending_question != retry_key:
                # Nothing verifiable in the answer — ask once more instead of
                # storing garbage and discovering schemes for state "Kjkn".
                widow.pending_question = retry_key
                reply = REASK[step][lang]
                db.add(Conversation(widow_id=widow_id, role="agent", content=reply))
                db.commit()
                log_action(
                    widow_id, "voice",
                    f"Couldn't understand the answer for step {step + 1}/5 — "
                    "asked again instead of guessing",
                )
                return {"agent_reply": reply, "done": False, "profile": None}
            if widow.pending_question == retry_key:
                widow.pending_question = None
            widow.onboarding_step = step + 1
            if widow.onboarding_step >= 5:
                done = True
                reply = DONE_MESSAGE[lang].format(name=widow.name or "")
                log_action(
                    widow_id,
                    "voice",
                    f"Onboarding complete for {widow.name} ({widow.state}) — profile saved",
                    {"profile": widow.to_dict()},
                )
            else:
                reply = QUESTIONS[lang][widow.onboarding_step].format(name=widow.name or "")

        db.add(Conversation(widow_id=widow_id, role="agent", content=reply))
        db.commit()
        profile = widow.to_dict()

    if not done:
        log_action(widow_id, "voice", f"Onboarding step {profile['onboarding_step']}/5 — listening")
    return {"agent_reply": reply, "done": done, "profile": profile if done else None}
