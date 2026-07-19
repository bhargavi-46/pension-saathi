"use client";

/** Voice input (SpeechRecognition) + output (speechSynthesis) for the chat.
 *  Web Speech API only works on HTTPS or localhost, Chrome/Edge. */

import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceLang = "hi-IN" | "te-IN" | "en-IN" | "ta-IN" | "bn-IN";

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
}

interface SpeechRecognitionEventLike {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}

export function useVoice(initialLang: VoiceLang = "hi-IN") {
  const [supported, setSupported] = useState(true);
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [lang, setLang] = useState<VoiceLang>(initialLang);
  const [autoSpeak, setAutoSpeak] = useState(true);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  // Unified speech queue: each task is either a browser SpeechSynthesisUtterance
  // OR a server-side Sarvam TTS request (Promise<HTMLAudioElement>). Both flow
  // through the same lock so we never speak two things at once — the bug
  // where Telugu messages overlapped came from server-TTS bypassing the lock.
  type BrowserTask = { kind: "browser"; utterance: SpeechSynthesisUtterance };
  type ServerTask = { kind: "server"; audioPromise: Promise<HTMLAudioElement | null> };
  type SpeechTask = BrowserTask | ServerTask;
  const speechQueueRef = useRef<SpeechTask[]>([]);
  const isSpeakingRef = useRef(false);
  // Chrome GC bug: utterances can be collected mid-speech unless referenced.
  const currentUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    const w = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Ctor) {
      setSupported(false);
      return;
    }
    const rec = new Ctor();
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (event) => {
      const text = Array.from({ length: event.results.length }, (_, i) =>
        event.results[i][0].transcript
      ).join(" ");
      setTranscript(text);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognitionRef.current = rec;

    // Chrome loads TTS voices asynchronously — getVoices() returns [] until
    // 'voiceschanged' fires. Warm the list so the first speak() can find a
    // Telugu/Hindi voice instead of falling back to a silent default.
    if (window.speechSynthesis) {
      window.speechSynthesis.getVoices();
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.getVoices();
      };
    }
  }, []);

  const startListening = useCallback(() => {
    const rec = recognitionRef.current;
    if (!rec) return;
    setTranscript("");
    rec.lang = lang;
    try {
      rec.start();
      setListening(true);
    } catch {
      /* already started */
    }
  }, [lang]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  const processSpeechQueue = useCallback(async () => {
    const queue = speechQueueRef.current;
    if (queue.length === 0) {
      isSpeakingRef.current = false;
      currentUtteranceRef.current = null;
      return;
    }
    isSpeakingRef.current = true;
    const task = queue.shift()!;
    if (task.kind === "browser") {
      currentUtteranceRef.current = task.utterance;
      task.utterance.onend = () => processSpeechQueue();
      task.utterance.onerror = () => processSpeechQueue();
      window.speechSynthesis.speak(task.utterance);
    } else {
      // Server TTS: audio was pre-fetched when speak() was called, so by
      // the time we get here the blob is (usually) already downloaded —
      // playback starts immediately. Guarantees no gap-then-clip.
      const audio = await task.audioPromise;
      if (!audio) {
        processSpeechQueue();
        return;
      }
      const cleanup = () => {
        if (audio.src.startsWith("blob:")) URL.revokeObjectURL(audio.src);
        processSpeechQueue();
      };
      audio.onended = cleanup;
      audio.onerror = cleanup;
      try {
        await audio.play();
      } catch {
        cleanup();
      }
    }
  }, []);

  /** Stop everything currently spoken or queued (used when auto-speak is
   *  switched off, or before speaking something the user explicitly tapped). */
  const stopSpeaking = useCallback(() => {
    speechQueueRef.current = [];
    isSpeakingRef.current = false;
    currentUtteranceRef.current = null;
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  }, []);

  /** Kick off a Sarvam TTS request immediately and return a Promise that
   *  resolves to a playback-ready Audio element. The fetch happens in
   *  parallel with any currently-playing speech, so by the time this task's
   *  turn comes up in the queue, the audio is already decoded — no more
   *  30-second Telugu delays. */
  const fetchServerAudio = useCallback(
    (text: string, effLang: VoiceLang): Promise<HTMLAudioElement | null> => {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const shortLang = effLang.split("-")[0]; // 'te-IN' → 'te'
      return fetch(`${apiBase}/voice/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang: shortLang }),
      })
        .then((r) => (r.ok ? r.blob() : null))
        .then((blob) => {
          if (!blob) return null;
          const audio = new Audio(URL.createObjectURL(blob));
          audio.preload = "auto";
          return new Promise<HTMLAudioElement>((resolve) => {
            if (audio.readyState >= 3) resolve(audio);
            else {
              audio.oncanplay = () => resolve(audio);
              setTimeout(() => resolve(audio), 500); // safety net
            }
          });
        })
        .catch(() => null);
    },
    []
  );

  const speak = useCallback(
    (text: string, force = false) => {
      if (typeof window === "undefined" || !window.speechSynthesis) return;
      if (!autoSpeak && !force) return;
      // Choose the voice from the TEXT's script, not the setting — avoids
      // stale-language timing issues and keeps speech truly dynamic.
      const effectiveLang: VoiceLang = /[ఀ-౿]/.test(text)
        ? "te-IN"
        : /[ऀ-ॿ]/.test(text)
          ? "hi-IN"
          : /[஀-௿]/.test(text)
            ? "ta-IN"
            : /[ঀ-৿]/.test(text)
              ? "bn-IN"
              : lang;
      const voices = window.speechSynthesis.getVoices();
      const langRoot = effectiveLang.split("-")[0];
      const preferred =
        voices.find((v) => v.lang === effectiveLang) ??
        voices.find((v) => v.lang.startsWith(langRoot));

      // Fallback: no matching voice on this OS (very common for te / ta / bn
      // on Windows/Mac) → route through the shared queue as a server-TTS
      // task. Fetch starts NOW so it downloads in parallel with anything
      // currently speaking.
      if (!preferred && langRoot !== "en") {
        speechQueueRef.current.push({
          kind: "server",
          audioPromise: fetchServerAudio(text, effectiveLang),
        });
      } else {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = effectiveLang;
        if (preferred) utterance.voice = preferred;
        speechQueueRef.current.push({ kind: "browser", utterance });
      }
      if (!isSpeakingRef.current) processSpeechQueue();
    },
    [lang, autoSpeak, processSpeechQueue, fetchServerAudio]
  );

  return {
    supported,
    listening,
    transcript,
    setTranscript,
    lang,
    setLang,
    autoSpeak,
    setAutoSpeak,
    startListening,
    stopListening,
    speak,
    stopSpeaking,
  };
}
