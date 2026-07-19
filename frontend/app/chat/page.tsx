"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, Claim, NON_CASH_SCHEME_IDS } from "@/lib/api";
import { useVoice, VoiceLang } from "@/hooks/useVoice";

interface Message {
  id: number;
  role: "user" | "agent";
  content: string;
  imageUrl?: string;
  time: string;
}

const DOC_LABELS: Record<string, Record<string, string>> = {
  hi: {
    death_certificate: "मृत्यु प्रमाण पत्र",
    aadhaar: "आधार कार्ड",
    bank_passbook: "बैंक पासबुक",
    ration_card: "राशन कार्ड",
  },
  te: {
    death_certificate: "మరణ ధృవీకరణ పత్రం",
    aadhaar: "ఆధార్ కార్డు",
    bank_passbook: "బ్యాంక్ పాస్‌బుక్",
    ration_card: "రేషన్ కార్డు",
  },
  en: {
    death_certificate: "Death Certificate",
    aadhaar: "Aadhaar Card",
    bank_passbook: "Bank Passbook",
    ration_card: "Ration Card",
  },
};

const DOC_ICONS: Record<string, string> = {
  death_certificate: "📄",
  aadhaar: "🪪",
  bank_passbook: "🏦",
  ration_card: "🍚",
};

function docLabel(docType: string, lang: string): string {
  const l = lang.split("-")[0];
  const labels = DOC_LABELS[l] ?? DOC_LABELS.en;
  return labels[docType] ?? DOC_LABELS.en[docType] ?? docType.replace("_", " ");
}

function docTypes(lang: string) {
  const l = lang.split("-")[0];
  const labels = DOC_LABELS[l] ?? DOC_LABELS.en;
  return Object.keys(DOC_ICONS).map((id) => ({
    id,
    icon: DOC_ICONS[id],
    label: l === "en" ? labels[id] : `${labels[id]} / ${DOC_LABELS.en[id]}`,
  }));
}

/** Scheme names are stored "हिंदी / English" (or "తెలుగు / English") — show
 *  the segment matching the user's language, falling back to English. */
function schemeDisplayName(name: string | null, lang: string): string {
  if (!name) return "—";
  const parts = name.split("/").map((p) => p.trim()).filter(Boolean);
  if (parts.length < 2) return name;
  const l = lang.split("-")[0];
  const script = l === "hi" ? /[ऀ-ॿ]/ : l === "te" ? /[ఀ-౿]/ : null;
  if (script) {
    const match = parts.find((p) => script.test(p));
    if (match) return match;
  }
  return parts[parts.length - 1];
}

const LANGS: { id: VoiceLang; label: string }[] = [
  { id: "hi-IN", label: "हिंदी" },
  { id: "te-IN", label: "తెలుగు" },
  { id: "en-IN", label: "English" },
  { id: "ta-IN", label: "தமிழ்" },
  { id: "bn-IN", label: "বাংলা" },
];

function now() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** App-generated Saathi messages in the selected language (falls back to English). */
function t(lang: string) {
  const l = lang.split("-")[0];
  const strings: Record<string, Record<string, string>> = {
    hi: {
      certConfirm:
        "मैंने प्रमाण पत्र पढ़ लिया है ✓ आपके पति {name} का देहांत {date} को हुआ (प्रमाण पत्र {cert}) — जानकारी सुरक्षित रख ली।",
      found:
        "मुझे {n} योजनाएँ मिलीं जिनकी आप हकदार हैं — यह कुल ₹{total} प्रति वर्ष की सुरक्षा राशि है। पैसा एकसाथ नहीं, साल भर किस्तों में आएगा, और हर बार मैं आपको बताऊँगी। अब देखती हूँ किनके लिए तुरंत आवेदन हो सकता है।",
      submitted:
        "✅ {n} योजनाओं के लिए मैंने अभी ऑनलाइन आवेदन कर दिया — ट्रैकिंग ID मिल गई हैं। डैशबोर्ड पर प्रगति देखें।",
      askDocs:
        "आगे बढ़ने के लिए मुझे इन दस्तावेज़ों की फोटो चाहिए: {docs}। कृपया 📎 बटन से भेजें।",
      askDocsScheme:
        "बहन, {scheme} के लिए आप हकदार हैं, पर आवेदन पूरा करने के लिए मुझे {docs} की फोटो चाहिए। कृपया 📎 बटन दबाकर भेजें — मिलते ही मैं आगे बढ़ाऊँगी।",
      actionNeeded:
        "⚠ {n} योजनाओं के लिए आपको खुद दफ़्तर जाना होगा। हर योजना के कार्ड पर लिखा है कहाँ जाना है और क्या ले जाना है।",
      docRead: "दस्तावेज़ मिल गया और पढ़ लिया ✓ ({info})",
      paymentReceived:
        "{name} बहन, खुशखबरी! 🎉 आपकी {scheme} की पहली किस्त ₹{amount} DBT के ज़रिए सीधे आपके बैंक खाते में आ गई है। (यह आपकी कुल ₹{total}/वर्ष सहायता का हिस्सा है — बाकी किस्तें आगे आती रहेंगी।)",
      healthActive:
        "{name} बहन, अच्छी खबर! 🏥 आपका {scheme} का गोल्डन कार्ड चालू हो गया है — अब आपको ₹5,00,000 तक का मुफ़्त इलाज मिलेगा।",
      paymentPending:
        "बाकी योजनाओं के लिए दस्तावेज़ तैयार हैं — ऊपर हर कार्ड पर लिखा है कहाँ जाना है। मैं आपके लिए सब ट्रैक करती रहूँगी। कोई भी मदद चाहिए तो यहीं संदेश भेजें।",
      attachTitle: "आप क्या भेज रही हैं?",
      placeholder: "संदेश लिखें…",
      intro: "नमस्ते कहकर शुरू करें 🙏",
      listenIntro: "बहन, परेशान मत होइए। ध्यान से सुनिए:",
    },
    te: {
      certConfirm:
        "నేను ధృవీకరణ పత్రం చదివాను ✓ మీ భర్త {name} గారు {date} న మరణించారు (సర్టిఫికెట్ {cert}) — వివరాలు భద్రంగా ఉన్నాయి.",
      found:
        "మీకు రావాల్సిన {n} పథకాలు దొరికాయి — ఇది సంవత్సరానికి మొత్తం ₹{total} భద్రతా మొత్తం. డబ్బు ఒకేసారి కాదు, ఏడాది పొడవునా వాయిదాలలో వస్తుంది, ప్రతిసారీ నేను మీకు చెబుతాను. ఇప్పుడు వేటికి వెంటనే దరఖాస్తు చేయవచ్చో చూస్తాను.",
      submitted:
        "✅ {n} పథకాలకు ఇప్పుడే ఆన్‌లైన్‌లో దరఖాస్తు చేశాను — ట్రాకింగ్ ID లు వచ్చాయి. డాష్‌బోర్డ్‌లో ప్రగతి చూడండి.",
      askDocs:
        "ముందుకు వెళ్ళడానికి ఈ పత్రాల ఫోటోలు కావాలి: {docs}. దయచేసి 📎 బటన్ ద్వారా పంపండి.",
      askDocsScheme:
        "అక్కా, మీరు {scheme} కు అర్హులు, కానీ దరఖాస్తు పూర్తి చేయడానికి {docs} ఫోటో కావాలి. దయచేసి 📎 బటన్ నొక్కి పంపండి — అందగానే నేను ముందుకు తీసుకెళ్తాను.",
      actionNeeded:
        "⚠ {n} పథకాలకు మీరు స్వయంగా కార్యాలయానికి వెళ్ళాలి. ఎక్కడికి వెళ్ళాలో, ఏమి తీసుకెళ్ళాలో ప్రతి పథకం కార్డులో ఉంది.",
      docRead: "పత్రం అందింది, చదివాను ✓ ({info})",
      paymentReceived:
        "{name} అక్కా, శుభవార్త! 🎉 మీ {scheme} మొదటి వాయిదా ₹{amount} DBT ద్వారా నేరుగా మీ బ్యాంక్ ఖాతాలో జమ అయ్యింది. (ఇది మీ మొత్తం ₹{total}/సంవత్సరం సహాయంలో భాగం — మిగతా వాయిదాలు తర్వాత వస్తాయి.)",
      healthActive:
        "{name} అక్కా, శుభవార్త! 🏥 మీ {scheme} గోల్డెన్ కార్డు యాక్టివ్ అయ్యింది — ఇప్పుడు ₹5,00,000 వరకు ఉచిత వైద్యం పొందవచ్చు.",
      paymentPending:
        "మిగతా పథకాలకు పత్రాలు సిద్ధంగా ఉన్నాయి — ప్రతి కార్డులో ఎక్కడికి వెళ్ళాలో ఉంది. నేను అన్నీ ట్రాక్ చేస్తూ ఉంటాను. ఏ సహాయం కావాలన్నా ఇక్కడే సందేశం పంపండి.",
      attachTitle: "మీరు ఏమి పంపుతున్నారు?",
      placeholder: "సందేశం రాయండి…",
      intro: "నమస్తే అని చెప్పి మొదలుపెట్టండి 🙏",
      listenIntro: "అక్కా, కంగారు పడకండి. జాగ్రత్తగా వినండి:",
    },
    en: {
      certConfirm:
        "I've read the certificate ✓ Your husband {name} passed away on {date} (certificate {cert}) — details saved.",
      found:
        "I found {n} schemes you are entitled to — a total safety-net of about ₹{total} per year. The money comes in installments through the year, not all at once, and I'll tell you each time some arrives. Now let me see which I can apply for right away.",
      submitted:
        "✅ I've applied online for {n} scheme(s) — tracking IDs issued. Watch progress on the dashboard.",
      askDocs:
        "To move forward I need photos of these documents: {docs}. Please send them using the 📎 button.",
      askDocsScheme:
        "Sister, you are eligible for {scheme}, but to complete the application I still need a photo of your {docs}. Please tap the 📎 button and send it — I'll continue as soon as it arrives.",
      actionNeeded:
        "⚠ {n} scheme(s) need you to visit an office in person. Each card shows exactly where to go and what to carry.",
      docRead: "Document received and read ✓ ({info})",
      paymentReceived:
        "{name} sister, wonderful news! 🎉 The first installment of ₹{amount} from your {scheme} has landed directly in your bank account via DBT. (This is part of your ₹{total}/year total — more installments will follow.)",
      healthActive:
        "{name} sister, good news! 🏥 Your {scheme} golden card is now active — you can get free treatment up to ₹5,00,000.",
      paymentPending:
        "For the other schemes the documents are ready — each card above shows where to go. I'll keep tracking everything for you. Message me here anytime you need help.",
      attachTitle: "What are you sending?",
      placeholder: "Message…",
      intro: "Say hello to begin 🙏",
      listenIntro: "Sister, don't worry. Listen carefully:",
    },
  };
  return strings[l] ?? strings.en;
}

function fill(template: string, vars: Record<string, string | number>) {
  return template.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? "—"));
}

/** The language the user actually types in wins over the settings toggle. */
function detectScriptLang(text: string): VoiceLang | null {
  if (/[ఀ-౿]/.test(text)) return "te-IN";
  if (/[ऀ-ॿ]/.test(text)) return "hi-IN";
  if (/[஀-௿]/.test(text)) return "ta-IN";
  if (/[ঀ-৿]/.test(text)) return "bn-IN";
  return null;
}

export default function ChatPage() {
  const [widowId, setWidowId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [thinkingLabel, setThinkingLabel] = useState("Saathi is typing…");
  const [onboardingDone, setOnboardingDone] = useState(false);
  const [certUploaded, setCertUploaded] = useState(false);
  const [discoveryRan, setDiscoveryRan] = useState(false);
  const [uploadedDocs, setUploadedDocs] = useState<Set<string>>(new Set());
  const [claims, setClaims] = useState<Claim[]>([]);
  const [showAttach, setShowAttach] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [pendingDocType, setPendingDocType] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [widowName, setWidowName] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLElement>(null);
  // User-intent scroll flag: auto-scroll only while she is already near the
  // bottom. If she scrolls up to re-read, new messages must not yank her down.
  const nearBottomRef = useRef(true);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const nextId = useRef(1);
  // English by default; switches automatically to whatever script she types in
  const voice = useVoice("en-IN");

  // Refs so the live payment listener always reads current values (no re-subscribe)
  const voiceRef = useRef(voice);
  voiceRef.current = voice;
  const widowNameRef = useRef("");
  widowNameRef.current = widowName;
  const paidIdsRef = useRef<Set<number>>(new Set());
  const pendingShownRef = useRef(false);
  const totalAnnualRef = useRef(0);
  const cardsShownRef = useRef(false);

  useEffect(() => {
    let id = localStorage.getItem("ps-widow-id");
    if (!id) {
      id = `w-${Math.random().toString(36).slice(2, 10)}`;
      localStorage.setItem("ps-widow-id", id);
    }
    setWidowId(id);
    // Recover the name on reconnect so payment messages address her by name.
    api.getWidow(id).then((p) => { if (p?.name) setWidowName(p.name); }).catch(() => {});
  }, []);

  const handleChatScroll = useCallback(() => {
    const el = chatContainerRef.current;
    if (!el) return;
    nearBottomRef.current =
      el.scrollHeight - el.scrollTop <= el.clientHeight + 100;
  }, []);

  useEffect(() => {
    if (nearBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, thinking, claims]);

  useEffect(() => {
    if (voice.transcript) setInput(voice.transcript);
  }, [voice.transcript]);

  const addMessage = useCallback(
    (role: "user" | "agent", content: string, imageUrl?: string) => {
      setMessages((prev) => [
        ...prev,
        { id: nextId.current++, role, content, imageUrl, time: now() },
      ]);
    },
    []
  );

  // Close the loop reliably: poll the claim state (the same source the
  // dashboard counter uses) and announce every claim that reaches "received"
  // exactly once — so the chat can never miss a payment the way transient
  // stream events can.
  useEffect(() => {
    if (!widowId) return;
    const check = async () => {
      let claims: Claim[];
      try {
        const res = await api.getClaims(widowId);
        claims = res.claims;
        // Populate the total on reconnect (it's otherwise set during discovery).
        if (!totalAnnualRef.current && res.total_annual_value) {
          totalAnnualRef.current = res.total_annual_value;
        }
      } catch {
        return;
      }
      setClaims(claims); // keep the live status cards fresh
      // On a reconnect the cards marker may be absent — insert it once.
      if (claims.length > 0 && !cardsShownRef.current) {
        cardsShownRef.current = true;
        addMessage("agent", "__CARDS__");
      }
      const v = voiceRef.current;
      const msgs = t(v.lang);
      for (const c of claims) {
        if (c.status !== "received" || paidIdsRef.current.has(c.id)) continue;
        paidIdsRef.current.add(c.id);
        if (NON_CASH_SCHEME_IDS.has(c.scheme_id)) {
          // Health cover activation, not a cash payout.
          const hm = fill(msgs.healthActive, {
            name: widowNameRef.current,
            scheme: schemeDisplayName(c.scheme_name, v.lang),
          });
          addMessage("agent", hm);
          v.speak(hm);
          continue;
        }
        const monthly = Math.max(Math.round(c.estimated_annual_value / 12), 300);
        const m = fill(msgs.paymentReceived, {
          name: widowNameRef.current,
          amount: monthly.toLocaleString("en-IN"),
          scheme: schemeDisplayName(c.scheme_name, v.lang),
          total: totalAnnualRef.current.toLocaleString("en-IN"),
        });
        addMessage("agent", m);
        v.speak(m);
      }
      // Once any money has arrived, remind her about the office-visit schemes.
      if (
        !pendingShownRef.current &&
        claims.some((c) => c.status === "received") &&
        claims.some((c) => c.status === "action_needed")
      ) {
        pendingShownRef.current = true;
        addMessage("agent", msgs.paymentPending);
      }
    };
    const iv = setInterval(check, 4000);
    return () => clearInterval(iv);
  }, [widowId, addMessage]);

  // Assess documents on file, submit what's ready, ask for what's missing.
  // Runs after discovery AND after every subsequent document upload.
  const runPrepare = useCallback(
    async (announce: boolean) => {
      const msgs = t(voice.lang);
      const result = await api.runPrepare(widowId);
      if (announce && result.submitted > 0) {
        const m = fill(msgs.submitted, { n: result.submitted });
        addMessage("agent", m);
        voice.speak(m);
      }
      if (result.pending_uploads && result.pending_uploads.length > 0 && result.pending_uploads.length <= 2) {
        // Interactive verification loop: one targeted follow-up per scheme,
        // naming the scheme and the exact document(s) still missing. The
        // claim stays halted (needs_documents) until she uploads them.
        for (const p of result.pending_uploads) {
          const docs = p.docs.map((d) => docLabel(d, voice.lang)).join(", ");
          const m = fill(msgs.askDocsScheme, { scheme: p.scheme, docs });
          addMessage("agent", m);
          voice.speak(m);
        }
      } else if (result.ask_for_uploads.length > 0) {
        const docs = result.ask_for_uploads
          .map((d) => docLabel(d, voice.lang))
          .join(", ");
        const m = fill(msgs.askDocs, { docs });
        addMessage("agent", m);
        voice.speak(m);
      } else if (announce && result.action_needed > 0) {
        addMessage("agent", fill(msgs.actionNeeded, { n: result.action_needed }));
      }
      const updated = await api.getClaims(widowId);
      setClaims(updated.claims);
    },
    [widowId, addMessage, voice]
  );

  const runDiscoveryAndPrepare = useCallback(async (force = false) => {
    if (discoveryRan && !force) return;
    setDiscoveryRan(true);
    const msgs = t(voice.lang);
    setThinkingLabel("Saathi is searching every scheme…");
    setThinking(true);
    try {
      const discovery = await api.runDiscovery(widowId);
      // Information gap: the pipeline HALTED and needs an answer before any
      // scheme is confirmed. Ask the follow-up question and wait — her reply
      // (handled in send()) resumes discovery with the completed profile.
      if (discovery.followup_question) {
        setDiscoveryRan(false);
        addMessage("agent", discovery.followup_question);
        voice.speak(discovery.followup_question);
        return;
      }
      totalAnnualRef.current = discovery.total_annual_value;
      const foundMsg = fill(msgs.found, {
        n: discovery.schemes_found,
        total: discovery.total_annual_value.toLocaleString("en-IN"),
      });
      addMessage("agent", foundMsg);
      voice.speak(foundMsg);
      setClaims(discovery.claims);
      // Anchor the live scheme-card panel here in the timeline, so later
      // status/payment messages appear below it instead of above.
      if (!cardsShownRef.current) {
        cardsShownRef.current = true;
        addMessage("agent", "__CARDS__");
      }
      await runPrepare(true);
    } catch {
      setError("Could not reach the Saathi backend. Is it running?");
    } finally {
      setThinking(false);
      setThinkingLabel("Saathi is typing…");
    }
  }, [widowId, addMessage, voice, discoveryRan, runPrepare]);

  const send = useCallback(
    async (text?: string) => {
      const message = (text ?? input).trim();
      if (!message || !widowId) return;
      // Reply language = language of THIS message (English for Latin text).
      // Letterless messages ("3200") keep the current language.
      const detected =
        detectScriptLang(message) ?? (/[A-Za-z]/.test(message) ? ("en-IN" as const) : null);
      // Only auto-flip the *conversation* language during onboarding, when we
      // still don't know what she prefers. Once onboarding is done, a stray
      // one-word Tamil (or English) reply during a Telugu conversation must
      // NOT drift the entire UI language — that's how you end up with the
      // "found 8 schemes" summary suddenly appearing in English.
      if (detected && detected !== voice.lang && !onboardingDone) {
        voice.setLang(detected);
      }
      setInput("");
      voice.setTranscript("");
      addMessage("user", message);
      setThinking(true);
      setError(null);
      try {
        const res = await api.onboardingMessage(widowId, message, voice.lang);
        addMessage("agent", res.agent_reply);
        voice.speak(res.agent_reply);
        if (res.done) {
          setOnboardingDone(true);
          if (res.profile?.name) setWidowName(res.profile.name);
          if (certUploaded) await runDiscoveryAndPrepare();
        } else if (res.resume_discovery) {
          // She answered the information-gap question — resume the halted
          // discovery pipeline with the now-complete profile.
          await runDiscoveryAndPrepare(true);
        }
      } catch {
        setError("Could not reach the Saathi backend. Is it running?");
      } finally {
        setThinking(false);
      }
    },
    [input, widowId, addMessage, voice, certUploaded, runDiscoveryAndPrepare]
  );

  const onFileSelected = useCallback(
    async (file: File) => {
      if (!pendingDocType) return;
      const docType = pendingDocType;
      setPendingDocType(null);
      const imageUrl = URL.createObjectURL(file);
      addMessage(
        "user",
        docTypes(voice.lang).find((d) => d.id === docType)?.label ?? docType,
        imageUrl
      );
      setThinkingLabel("Saathi is reading the document…");
      setThinking(true);
      setError(null);
      try {
        let res;
        try {
          res = await api.uploadDocument(widowId, docType, file);
        } catch (e) {
          // Free-tier rate limit: wait it out once instead of failing the flow
          if (e instanceof Error && /limit|429/i.test(e.message)) {
            setThinkingLabel("⏳ Free-tier limit — retrying in 1 minute, please wait…");
            await new Promise((r) => setTimeout(r, 65000));
            setThinkingLabel("Saathi is reading the document…");
            res = await api.uploadDocument(widowId, docType, file);
          } else {
            throw e;
          }
        }
        const d = res.extracted_data;
        const msgs = t(voice.lang);
        setUploadedDocs((prev) => new Set(prev).add(docType));
        if (docType === "death_certificate") {
          setCertUploaded(true);
          const confirmMsg = fill(msgs.certConfirm, {
            name: d.deceased_name ?? "—",
            date: d.date_of_death ?? "—",
            cert: d.certificate_number ?? "—",
          });
          addMessage("agent", confirmMsg);
          voice.speak(confirmMsg);
          if (onboardingDone) await runDiscoveryAndPrepare();
        } else {
          addMessage(
            "agent",
            fill(msgs.docRead, { info: d.name ?? d.account_holder_name ?? "details extracted" })
          );
          // Re-assess: a new document may make more schemes ready to submit.
          if (discoveryRan) await runPrepare(true);
        }
      } catch (e) {
        setError(
          e instanceof Error && e.message && !e.message.startsWith("upload failed")
            ? e.message
            : "Could not read the document. Please try a clearer photo."
        );
      } finally {
        setThinking(false);
        setThinkingLabel("Saathi is typing…");
      }
    },
    [pendingDocType, widowId, addMessage, onboardingDone, runDiscoveryAndPrepare, runPrepare, discoveryRan, voice]
  );

  const reset = useCallback(() => {
    localStorage.removeItem("ps-widow-id");
    window.location.reload();
  }, []);

  const statusBadge: Record<Claim["status"], string> = {
    discovered: "bg-amber-100 text-amber-800",
    needs_documents: "bg-orange-100 text-orange-800",
    action_needed: "bg-rose-100 text-rose-800",
    filed: "bg-blue-100 text-blue-800",
    tracking: "bg-purple-100 text-purple-800",
    received: "bg-green-100 text-green-800",
    rejected: "bg-red-100 text-red-800",
  };
  const statusLabel: Record<Claim["status"], string> = {
    discovered: "Discovered",
    needs_documents: "Docs needed",
    action_needed: "Visit office",
    filed: "Submitted",
    tracking: "Tracking",
    received: "Received ✓",
    rejected: "Rejected",
  };

  return (
    <div className="mx-auto flex h-dvh max-w-md flex-col bg-[#ECE5DD]">
      {/* Top bar */}
      <header className="flex items-center gap-3 bg-wa-green px-4 py-3 text-white shadow">
        <Link href="/" className="text-xl" aria-label="Home">←</Link>
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gold text-lg font-bold">
          स
        </div>
        <div className="flex-1">
          <div className="font-semibold">Saathi</div>
          <div className="flex items-center gap-1 text-xs text-green-200">
            <span className="h-2 w-2 rounded-full bg-green-400" /> online · Pension Saathi
          </div>
        </div>
        {widowId && (
          <Link
            href={`/dashboard/${widowId}`}
            className="rounded bg-white/15 px-2 py-1 text-xs hover:bg-white/25"
            target="_blank"
          >
            Dashboard
          </Link>
        )}
        <button
          onClick={() => setShowSettings((s) => !s)}
          className="text-lg"
          aria-label="Settings"
        >
          ⚙️
        </button>
      </header>

      {showSettings && (
        <div className="border-b bg-white px-4 py-3 text-sm shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <span>Auto-speak replies</span>
            <button
              onClick={() => {
                if (voice.autoSpeak) voice.stopSpeaking();
                voice.setAutoSpeak(!voice.autoSpeak);
              }}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                voice.autoSpeak ? "bg-wa-green text-white" : "bg-gray-200"
              }`}
            >
              {voice.autoSpeak ? "ON" : "OFF"}
            </button>
          </div>
          <div className="mb-2 flex items-center gap-2">
            <span>Language:</span>
            {LANGS.map((l) => (
              <button
                key={l.id}
                onClick={() => voice.setLang(l.id)}
                className={`rounded px-2 py-1 text-xs ${
                  voice.lang === l.id ? "bg-wa-green text-white" : "bg-gray-100"
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>
          <button onClick={reset} className="text-xs text-red-600 underline">
            New conversation (reset)
          </button>
        </div>
      )}

      {/* Chat area */}
      <main
        ref={chatContainerRef}
        onScroll={handleChatScroll}
        className="flex-1 space-y-2 overflow-y-auto px-3 py-4"
      >
        {messages.length === 0 && (
          <div className="mx-auto mt-8 max-w-xs rounded-lg bg-white/80 p-4 text-center text-sm text-gray-600 shadow">
            {t(voice.lang).intro}
            <br />
            Say <b>hello</b> (or hold 🎤 and speak) to begin.
          </div>
        )}
        {messages.map((m) =>
          m.content === "__CARDS__" ? (
            <div key={m.id} className="space-y-2 pt-1">
              {claims.map((c) => (
                <div key={c.id} className="rounded-lg border border-gold/30 bg-white p-3 shadow-sm">
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-sm font-semibold text-aubergine">
                      {schemeDisplayName(c.scheme_name, voice.lang)}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        onClick={() => {
                          // An explicit tap jumps the queue — stop whatever is
                          // playing and speak this card immediately.
                          voice.stopSpeaking();
                          voice.speak(
                            `${t(voice.lang).listenIntro} ${schemeDisplayName(c.scheme_name, voice.lang)}. ${c.reasoning ?? ""} ${c.notes ?? ""}`,
                            true
                          );
                        }}
                        className="text-sm"
                        aria-label="Listen"
                        title="Listen"
                      >
                        🔊
                      </button>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${statusBadge[c.status]}`}>
                        {statusLabel[c.status]}
                      </span>
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-gray-600">{c.reasoning}</div>
                  {c.notes && (
                    <div
                      className={`mt-1 whitespace-pre-line rounded px-2 py-1 text-[11px] ${
                        c.status === "action_needed"
                          ? "bg-rose-50 text-rose-900"
                          : "bg-amber-50 text-amber-900"
                      }`}
                    >
                      {c.status === "action_needed" ? "🏢 " : "📄 "}
                      {c.notes}
                    </div>
                  )}
                  <div className="mt-1 flex items-center justify-between text-xs">
                    <span className="font-semibold text-gold">
                      ₹{c.estimated_annual_value.toLocaleString("en-IN")}/year
                    </span>
                    {c.tracking_id && <span className="font-mono text-gray-500">{c.tracking_id}</span>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 shadow-sm ${
                  m.role === "user" ? "rounded-tr-none bg-wa-bubble" : "rounded-tl-none bg-white"
                }`}
              >
                {m.imageUrl && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={m.imageUrl} alt="uploaded document" className="mb-1 max-h-48 rounded" />
                )}
                <div className="whitespace-pre-wrap text-sm">{m.content}</div>
                <div className="mt-0.5 text-right text-[10px] text-gray-400">{m.time}</div>
              </div>
            </div>
          )
        )}

        {thinking && (
          <div className="flex justify-start">
            <div className="rounded-lg rounded-tl-none bg-white px-3 py-2 text-sm text-gray-500 shadow-sm">
              <span className="animate-pulse">{thinkingLabel}</span>
            </div>
          </div>
        )}

        {error && (
          <div className="mx-auto max-w-xs rounded bg-red-50 p-2 text-center text-xs text-red-700">
            {error}
          </div>
        )}
        <div ref={bottomRef} />
      </main>

      {/* Input bar */}
      <footer className="flex items-center gap-2 bg-[#F0F0F0] px-2 py-2">
        <button
          onClick={() => setShowAttach(true)}
          className="flex h-10 w-10 items-center justify-center rounded-full text-xl text-gray-600 hover:bg-gray-200"
          aria-label="Attach document"
        >
          📎
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={voice.listening ? "🎙️ Listening…" : t(voice.lang).placeholder}
          className="h-10 flex-1 rounded-full border-none bg-white px-4 text-sm outline-none"
        />
        {voice.supported ? (
          <button
            onMouseDown={voice.startListening}
            onMouseUp={voice.stopListening}
            onTouchStart={voice.startListening}
            onTouchEnd={voice.stopListening}
            className={`flex h-10 w-10 items-center justify-center rounded-full text-xl ${
              voice.listening ? "animate-pulse bg-red-500 text-white" : "text-gray-600 hover:bg-gray-200"
            }`}
            aria-label="Hold to speak"
            title="Press and hold to speak"
          >
            🎤
          </button>
        ) : (
          <span className="px-1 text-[10px] text-gray-400">voice n/a</span>
        )}
        <button
          onClick={() => send()}
          disabled={!input.trim() || thinking}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-wa-green text-white disabled:opacity-40"
          aria-label="Send"
        >
          ➤
        </button>
      </footer>

      {/* Attach dialog */}
      {showAttach && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40"
          onClick={() => setShowAttach(false)}
        >
          <div
            className="mb-4 w-full max-w-sm rounded-xl bg-white p-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 text-center font-semibold">{t(voice.lang).attachTitle}</div>
            {docTypes(voice.lang).map((d) => (
              <button
                key={d.id}
                onClick={() => {
                  setPendingDocType(d.id);
                  setShowAttach(false);
                  fileInputRef.current?.click();
                }}
                className="mb-2 flex w-full items-center gap-3 rounded-lg border p-3 text-left text-sm hover:bg-soft-pink"
              >
                <span className="text-2xl">{d.icon}</span> {d.label}
              </button>
            ))}
          </div>
        </div>
      )}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFileSelected(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}
