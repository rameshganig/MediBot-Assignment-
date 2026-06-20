'use client';
import React, { useState, useEffect, useRef } from 'react';
import { AlertCircle, ArrowUpRight, BadgeInfo, CheckCircle2, Circle, Copy, Link2, LogOut, MessageSquareText, SendHorizonal, ShieldCheck, Sparkles, Stethoscope, Waves } from 'lucide-react';

const COLLECTION_COPY: Record<string, string> = {
  general: 'HR and policy references available to all staff.',
  clinical: 'Treatment protocols, drug formulary, and diagnostic guidance.',
  nursing: 'Nursing procedures and ICU care guidance.',
  billing: 'Insurance claims, billing rules, and financial references.',
  equipment: 'Equipment operation, calibration, and maintenance manuals.',
};

// ---------------- DEMO ACCOUNTS ----------------
const DEMO_ACCOUNTS = [
  { username: 'admin_user', password: 'password123', role: 'admin' },
  { username: 'billing_user', password: 'password123', role: 'billing_executive' },
  { username: 'doctor_user', password: 'password123', role: 'doctor' },
  { username: 'nurse_user', password: 'password123', role: 'nurse' },
  { username: 'tech_user', password: 'password123', role: 'technician' },
];

const API_BASE = 'http://localhost:8002';

// ---------------- TYPES ----------------
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

interface SourceItem {
  source_document: string;
  section_title: string;
  collection: string;
}

export default function MediBotPortal() {
  // ---------------- AUTH STATE ----------------
  const [token, setToken] = useState<string | null>(null);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [loginUser, setLoginUser] = useState('');
  const [loginPass, setLoginPass] = useState('');
  const [authError, setAuthError] = useState<string | null>(null);
  const [isLoggingIn, setIsLoggingIn] = useState(false);

  // ---------------- CHAT STATE ----------------
  const [messages, setMessages] = useState<Message[]>([]);
  const [sourcesByMessageId, setSourcesByMessageId] = useState<Record<string, SourceItem[]>>({});
  const [retrievalTypeByMessageId, setRetrievalTypeByMessageId] = useState<Record<string, string>>({});
  const [inputMessage, setInputMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [accessibleCollections, setAccessibleCollections] = useState<string[]>([]);
  const [lastCopiedMessageId, setLastCopiedMessageId] = useState<string | null>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ---------------- DEMO FILL ----------------
  const fillDemoAccount = (acc: (typeof DEMO_ACCOUNTS)[number]) => {
    setLoginUser(acc.username);
    setLoginPass(acc.password);
  };

  const loadCollectionsForRole = async (role: string) => {
    try {
      const res = await fetch(`${API_BASE}/collections/${role}`);
      if (!res.ok) return [];
      return (await res.json()) as string[];
    } catch {
      return [];
    }
  };

  // ---------------- LOGIN ----------------
  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);

    if (!loginUser || !loginPass) {
      setAuthError('Please fill all fields');
      return;
    }

    setIsLoggingIn(true);

    try {
      const res = await fetch(`${API_BASE}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => null);
        setAuthError(err?.detail || 'Login failed');
        return;
      }

      const data = await res.json().catch(() => null);

      if (!data?.session_token || !data?.role) {
        setAuthError('Invalid login response from server');
        return;
      }

      setToken(data.session_token);
      setUserRole(data.role);
      const collections = await loadCollectionsForRole(data.role);
      setAccessibleCollections(collections);
      setSourcesByMessageId({});
      setRetrievalTypeByMessageId({});
      setMessages([
        {
          id: 'welcome',
          role: 'assistant',
          content: 'Welcome to MediBot. Ask your question below.',
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    } catch {
      setAuthError('Server not reachable');
    } finally {
      setIsLoggingIn(false);
    }
  };

  // ---------------- LOGOUT ----------------
  const handleLogout = () => {
    setToken(null);
    setUserRole(null);
    setMessages([]);
    setSourcesByMessageId({});
    setRetrievalTypeByMessageId({});
    setLoginUser('');
    setLoginPass('');
    setAuthError(null);
    setInputMessage('');
    setAccessibleCollections([]);
    setLastCopiedMessageId(null);
  };

  const copyMessage = async (messageId: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setLastCopiedMessageId(messageId);
      window.setTimeout(() => {
        setLastCopiedMessageId((current) => (current === messageId ? null : current));
      }, 1800);
    } catch {
      setLastCopiedMessageId(null);
    }
  };

  // ---------------- SEND MESSAGE ----------------
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || isSending || !userRole || !token) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: inputMessage,
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputMessage('');
    setIsSending(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: userMsg.content, role: userRole }),
      });

      if (!res.ok) {
        throw new Error('Failed to fetch response');
      }

      const data = await res.json();
      const retrievalType = data.retrieval_type || 'hybrid_rag';
      const sources = Array.isArray(data.sources) ? data.sources : [];
      const botMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: data.answer || 'No response',
        timestamp: new Date().toLocaleTimeString(),
      };
      setSourcesByMessageId((prev) => ({
        ...prev,
        [botMsg.id]: sources,
      }));
      setRetrievalTypeByMessageId((prev) => ({
        ...prev,
        [botMsg.id]: retrievalType,
      }));
      setMessages((prev) => [...prev, botMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: 'Error contacting server',
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  // =====================================================
  // RENDERING LOGIC
  // =====================================================

  const roleLabel = userRole ? userRole.replace('_', ' ') : '';

  const renderCollectionPill = (collection: string) => (
    <div key={collection} className="rounded-full border border-slate-700/70 bg-slate-950/60 px-3 py-1 text-[11px] text-slate-300">
      <span className="capitalize text-teal-300">{collection}</span>
      <span className="ml-2 text-slate-500">{COLLECTION_COPY[collection] || 'Accessible collection'}</span>
    </div>
  );

  // 1. If not logged in -> Show Login Portal Layout
  if (!token) {
    return (
      <div className="min-h-screen w-screen overflow-hidden text-white">
        <div className="absolute inset-0 soft-grid opacity-35" />
        <div className="relative mx-auto flex min-h-screen w-full max-w-2xl items-center justify-center px-4 py-6 sm:px-6 lg:px-8">
          <section className="fade-up glass-panel w-full rounded-[28px] p-8 md:p-10">
            <div className="flex flex-col items-center text-center">
              <div className="pulse-ring rounded-2xl bg-teal-400/10 p-3">
                <Stethoscope className="h-7 w-7 text-teal-300" />
              </div>
              <h1 className="mt-5 text-4xl font-semibold tracking-tight text-slate-50 md:text-5xl">MediBot</h1>
            </div>

            <form onSubmit={handleLoginSubmit} className="mx-auto mt-8 max-w-md space-y-4">
              <FieldLabel label="Username" />
              <input
                type="text"
                value={loginUser}
                onChange={(e) => setLoginUser(e.target.value)}
                className="w-full rounded-2xl border border-slate-700/70 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-teal-400/60 focus:ring-2 focus:ring-teal-400/10"
                placeholder="Enter username"
              />

              <FieldLabel label="Password" />
              <input
                type="password"
                value={loginPass}
                onChange={(e) => setLoginPass(e.target.value)}
                className="w-full rounded-2xl border border-slate-700/70 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-teal-400/60 focus:ring-2 focus:ring-teal-400/10"
                placeholder="Enter password"
              />

              {authError && (
                <div className="flex items-start gap-2 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
                  <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                  <span>{authError}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={isLoggingIn}
                className="group inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-teal-500 to-cyan-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:from-teal-400 hover:to-cyan-400 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {isLoggingIn ? 'Logging in...' : 'Launch MediBot'}
                {!isLoggingIn && <ArrowUpRight className="h-4 w-4 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />}
              </button>
            </form>
          </section>
        </div>
      </div>
    );
  }

  // 2. If logged in -> Show New Centered Chat Layout
  return (
    <div className="h-screen w-screen overflow-hidden text-white">
      <div className="absolute inset-0 soft-grid opacity-30" />
      <div className="relative mx-auto flex h-screen w-full max-w-7xl gap-6 px-4 py-4 sm:px-6 lg:px-8 lg:py-6">
        <aside className="fade-up glass-panel hidden h-full min-h-0 w-[330px] shrink-0 flex-col rounded-[28px] p-5 lg:flex">
          <div className="flex items-center gap-3 border-b border-slate-700/50 pb-5">
            <div className="rounded-2xl bg-teal-400/10 p-3">
              <Stethoscope className="h-6 w-6 text-teal-300" />
            </div>
            <div>
              <div className="text-xs uppercase tracking-[0.28em] text-slate-500">Workspace</div>
              <div className="mt-1 text-lg font-semibold text-slate-50">MediBot Portal</div>
            </div>
          </div>

          <div className="mt-5 rounded-3xl border border-slate-700/60 bg-slate-950/60 p-4">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.28em] text-slate-500">
              <Circle className="h-2.5 w-2.5 fill-emerald-400 text-emerald-400" /> Live session
            </div>
            <div className="mt-3 text-sm text-slate-300">Signed in as</div>
            <div className="mt-1 text-xl font-semibold text-slate-50">{roleLabel}</div>
            <div className="mt-3 rounded-2xl border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-xs text-slate-400">
              Session token is active. Questions will be routed by role.
            </div>
          </div>

          <div className="mt-5 rounded-3xl border border-slate-700/60 bg-slate-950/60 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
              <ShieldCheck className="h-4 w-4 text-teal-300" /> Accessible collections
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {accessibleCollections.length ? accessibleCollections.map(renderCollectionPill) : (
                <div className="text-sm text-slate-500">No collections loaded.</div>
              )}
            </div>
          </div>

          <div className="mt-auto border-t border-slate-700/50 pt-4">
            <button
              onClick={handleLogout}
              className="flex w-full items-center justify-center gap-2 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm font-medium text-rose-200 transition hover:bg-rose-500/20"
            >
              <LogOut className="h-4 w-4" /> Logout
            </button>
          </div>
        </aside>

        <main className="fade-up glass-panel flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-[28px]">
          <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-700/60 px-5 py-5 md:px-6">
            <div className="flex items-center gap-4">
              <div className="rounded-2xl bg-teal-400/10 p-3">
                <Stethoscope className="h-6 w-6 text-teal-300" />
              </div>
              <div>
                <div className="text-xs uppercase tracking-[0.3em] text-slate-500">MediBot staff assistant</div>
                <div className="mt-1 flex items-center gap-3">
                  <h1 className="text-2xl font-semibold tracking-tight text-slate-50">MediBot Assistant</h1>
                  <span className="rounded-full border border-teal-400/30 bg-teal-400/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.2em] text-teal-200">
                    {retrievalTypeByMessageId[messages[messages.length - 1]?.id] === 'sql_rag' ? 'SQL RAG' : 'Hybrid RAG'}
                  </span>
                </div>
              </div>
            </div>
          </header>

          <div className="chat-history min-h-0 flex-1 overflow-y-scroll px-4 py-5 md:px-6">
            <div className="space-y-4">
              {messages.map((m, index) => (
                <div
                  key={m.id}
                  className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} fade-up`}
                  style={{ animationDelay: `${Math.min(index * 40, 180)}ms` }}
                >
                  <div className={`max-w-[min(100%,860px)] ${m.role === 'user' ? 'ml-10 text-right' : 'mr-10 text-left'}`}>
                    <div className={`rounded-[26px] border px-4 py-4 shadow-lg ${m.role === 'user' ? 'border-teal-400/20 bg-gradient-to-br from-teal-500 to-cyan-500 text-slate-950' : 'border-slate-700/70 bg-slate-950/75 text-slate-100'}`}>
                      <div className={`flex items-center gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-between'}`}>
                        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] opacity-80">
                          {m.role === 'user' ? 'You' : 'MediBot'}
                        </div>
                        <button
                          type="button"
                          onClick={() => copyMessage(m.id, m.content)}
                          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition ${m.role === 'user' ? 'border-slate-950/10 bg-slate-950/10 text-slate-950 hover:bg-slate-950/15' : 'border-slate-700/70 bg-slate-900/80 text-slate-300 hover:border-teal-400/40 hover:text-white'}`}
                        >
                          <Copy className="h-3.5 w-3.5" /> {lastCopiedMessageId === m.id ? 'Copied' : 'Copy'}
                        </button>
                      </div>
                      <div className="mt-3 whitespace-pre-wrap text-sm leading-7">{m.content}</div>
                    </div>

                    {/* Assistant responses intentionally shown without source/trace details for a cleaner chat view. */}
                  </div>
                </div>
              ))}
              <div ref={chatBottomRef} />
            </div>
          </div>

          <form onSubmit={handleSendMessage} className="border-t border-slate-700/60 bg-slate-950/40 p-4 md:p-5">
            <div className="flex items-end gap-3 rounded-[26px] border border-slate-700/70 bg-slate-950/80 p-3 shadow-2xl shadow-slate-950/20">
              <div className="flex-1">
                <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-[0.24em] text-slate-500">
                  <Waves className="h-3.5 w-3.5 text-teal-300" /> Prompt
                </div>
                <input
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  placeholder="Ask MediBot about policy, claims, or procedures..."
                  className="w-full rounded-2xl border border-slate-700/70 bg-slate-900/80 px-4 py-4 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-teal-400/60 focus:ring-2 focus:ring-teal-400/10"
                />
              </div>
              <button
                type="submit"
                disabled={isSending}
                className="inline-flex h-[52px] items-center gap-2 rounded-2xl bg-gradient-to-r from-teal-500 to-cyan-500 px-5 text-sm font-semibold text-slate-950 transition hover:from-teal-400 hover:to-cyan-400 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {isSending ? 'Sending...' : 'Send'}
                <SendHorizonal className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-700/60 bg-slate-950/60 px-4 py-3 text-xs text-slate-400">
              <div>
                Signed in as <span className="font-semibold text-slate-200">{loginUser || 'Unknown user'}</span>
              </div>
              <div>
                User type: <span className="font-semibold capitalize text-teal-200">{roleLabel || 'Unknown'}</span>
              </div>
            </div>
          </form>
        </main>
      </div>
    </div>
  );
}

function FieldLabel({ label }: { label: string }) {
  return <div className="text-xs font-medium uppercase tracking-[0.24em] text-slate-500">{label}</div>;
}

function WaveIcon() {
  return <MessageSquareText className="h-5 w-5 text-sky-300" />;
}
