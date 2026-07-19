import Link from "next/link";

const AGENTS = [
  {
    icon: "🔍",
    name: "Discovery Agent",
    desc: "Semantically searches 19 real government schemes and reasons about her eligibility for each one.",
  },
  {
    icon: "📄",
    name: "Document Agent",
    desc: "Reads a photo of a death certificate or Aadhaar with Gemini Vision — Hindi or English.",
  },
  {
    icon: "📮",
    name: "Filing Agent",
    desc: "Files every eligible claim and issues a tracking ID, so nothing depends on her chasing offices.",
  },
  {
    icon: "📡",
    name: "Tracking Agent",
    desc: "Keeps checking claim status day after day and tells her the moment money lands.",
  },
  {
    icon: "🎙️",
    name: "Voice Agent",
    desc: "Talks with her in Hindi, Tamil or Bengali — voice-first, because forms failed her already.",
  },
];

const STEPS = [
  { n: "1", title: "Upload", desc: "She sends one photo — her husband's death certificate — over a WhatsApp-style chat." },
  { n: "2", title: "Discover", desc: "Agents find every central and state scheme she is entitled to, and explain why." },
  { n: "3", title: "Receive", desc: "Claims are filed, tracked, and escalated until the money reaches her bank account." },
];

export default function Home() {
  return (
    <div className="min-h-dvh bg-background">
      {/* Hero */}
      <section className="bg-aubergine px-6 py-20 text-center text-white">
        <div className="mx-auto max-w-3xl">
          <div className="mb-3 text-sm uppercase tracking-[0.3em] text-gold-light">
            Pension Saathi · पेंशन साथी
          </div>
          <h1 className="font-[family-name:var(--font-playfair)] text-4xl font-bold leading-tight md:text-6xl">
            Every rupee she is owed.
            <br />
            <span className="text-gold">Found. Filed. Followed up.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-lg text-gray-300">
            An agentic AI companion that discovers, files and tracks every
            government pension entitlement for Indian widows — in her own
            language, from one photo.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link
              href="/chat"
              className="rounded-full bg-gold px-8 py-3 font-semibold text-aubergine transition hover:bg-gold-light"
            >
              Try as Widow →
            </Link>
            <Link
              href="/dashboard/demo-widow"
              className="rounded-full border border-gold px-8 py-3 font-semibold text-gold transition hover:bg-gold/10"
            >
              Judge Dashboard Demo
            </Link>
          </div>
        </div>
      </section>

      {/* Problem */}
      <section className="px-6 py-16">
        <div className="mx-auto grid max-w-4xl gap-6 text-center md:grid-cols-3">
          {[
            { stat: "1.5 crore", label: "widows in India eligible for pensions" },
            { stat: "70%", label: "never receive what they are entitled to" },
            { stat: "₹50,000 crore", label: "in entitlements stuck every year" },
          ].map((s) => (
            <div key={s.stat} className="rounded-2xl bg-soft-pink p-8">
              <div className="font-[family-name:var(--font-playfair)] text-4xl font-bold text-aubergine">
                {s.stat}
              </div>
              <div className="mt-2 text-sm text-gray-600">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="bg-white px-6 py-16">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center font-[family-name:var(--font-playfair)] text-3xl font-bold text-aubergine">
            How it works
          </h2>
          <div className="mt-10 grid gap-8 md:grid-cols-3">
            {STEPS.map((s) => (
              <div key={s.n} className="text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-gold text-xl font-bold text-white">
                  {s.n}
                </div>
                <h3 className="mt-4 text-lg font-semibold text-aubergine">{s.title}</h3>
                <p className="mt-2 text-sm text-gray-600">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Agents */}
      <section className="px-6 py-16">
        <div className="mx-auto max-w-5xl">
          <h2 className="text-center font-[family-name:var(--font-playfair)] text-3xl font-bold text-aubergine">
            Meet the five agents
          </h2>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {AGENTS.map((a) => (
              <div key={a.name} className="rounded-2xl border border-gold/20 bg-white p-6 shadow-sm">
                <div className="text-3xl">{a.icon}</div>
                <h3 className="mt-3 font-semibold text-aubergine">{a.name}</h3>
                <p className="mt-2 text-sm text-gray-600">{a.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Transparency */}
      <section className="bg-aubergine px-6 py-12 text-center text-white">
        <h2 className="font-[family-name:var(--font-playfair)] text-2xl font-bold text-gold">
          Built in the open
        </h2>
        <p className="mx-auto mt-3 max-w-lg text-sm text-gray-300">
          Gemini 2.0 Flash · LangGraph · ChromaDB · FastAPI · Next.js — all free
          and open-source, fully attributed.
        </p>
        <div className="mt-6 flex justify-center gap-6 text-sm">
          <a
            href="https://github.com/bhargavi-46/pension-saathi"
            className="text-gold underline hover:text-gold-light"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub repo
          </a>
          <a
            href="https://github.com/bhargavi-46/pension-saathi/blob/main/ATTRIBUTIONS.md"
            className="text-gold underline hover:text-gold-light"
            target="_blank"
            rel="noopener noreferrer"
          >
            Attributions
          </a>
        </div>
      </section>

      <footer className="bg-[#2b0f1f] px-6 py-6 text-center text-xs text-gray-400">
        Piridi Bhargavi · Solo build · <span className="text-gold">ScriptedByHer 2.0</span> (Meesho) ·
        &ldquo;She has been waiting. Let&rsquo;s stop making her wait.&rdquo;
      </footer>
    </div>
  );
}
