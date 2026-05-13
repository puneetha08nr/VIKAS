'use client'

import { useState, useRef, useEffect } from 'react'
import { axiosInstance } from '@/lib/api'

interface Message {
  id: string
  role: 'user' | 'bot'
  text: string
  intent?: string
  suggestions?: string[]
  timestamp: Date
}

interface LeadForm {
  name: string
  phone: string
  email: string
  company?: string
}

type BotRole = 'user' | 'admin'
type ChatStep = 'prechat' | 'chat' | 'feedback'

const TOPIC_BUBBLES = [
  { label: 'How does it work?', icon: '⚙️' },
  { label: 'What can Vikas generate?', icon: '✍️' },
  { label: 'How long does content take?', icon: '⏱️' },
  { label: 'Does it publish automatically?', icon: '🚀' },
  { label: 'What integrations are supported?', icon: '🔗' },
  { label: 'Show my content stats', icon: '📊' },
  { label: 'How does keyword research work?', icon: '🔍' },
  { label: 'Talk to someone', icon: '📞' },
]

const WELCOME_USER = `Hi! I'm Vikas AI assistant 👋

I can help you with:
• Understanding how Vikas works
• Your keywords and content stats
• Generating content
• Connecting you with our team

Pick a topic or type your question:`

const WELCOME_ADMIN = `Welcome back, Admin 🛠️

I have access to your system data. I can help with:
• Agent run status and errors
• LLM costs and token usage
• Pipeline troubleshooting
• DB queries and stats

What do you need?`

export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [botRole, setBotRole] = useState<BotRole>('user')
  const [step, setStep] = useState<ChatStep>('prechat')
  const [leadForm, setLeadForm] = useState<LeadForm>({ name: '', phone: '', email: '' })
  const [prechatErrors, setPrechatErrors] = useState<Partial<LeadForm>>({})
  const [showFeedback, setShowFeedback] = useState(false)
  const [feedbackRating, setFeedbackRating] = useState(0)
  const [unread, setUnread] = useState(0)
  const [savingLead, setSavingLead] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (open) {
      setUnread(0)
      if (step === 'chat' && messages.length === 0) {
        addBotMessage(botRole === 'admin' ? WELCOME_ADMIN : WELCOME_USER)
      }
      if (step === 'chat') inputRef.current?.focus()
    }
  }, [open, step])

  const handlePrechatSubmit = async () => {
    const errors: Partial<LeadForm> = {}
    if (!leadForm.name.trim()) errors.name = 'Required'
    if (!leadForm.phone.trim()) errors.phone = 'Required'
    if (!leadForm.email.trim()) errors.email = 'Required'
    if (Object.keys(errors).length > 0) { setPrechatErrors(errors); return }

    setSavingLead(true)
    const sid = crypto.randomUUID()
    setSessionId(sid)
    try {
      await axiosInstance.post('/api/v1/chat/lead', { ...leadForm, session_id: sid })
    } catch (_) { /* ignore — still proceed to chat */ }
    setSavingLead(false)
    setStep('chat')
    setTimeout(() => {
      addBotMessage(
        `Hi ${leadForm.name}! 👋 Welcome to Vikas.\n\nI can help you with keywords, content creation, opportunities, and more.\n\nWhat would you like to know?`,
        ['How does Vikas work?', 'What can you generate?', 'Show my content stats']
      )
    }, 100)
  }

  const addBotMessage = (text: string, suggestions?: string[], intent?: string) => {
    setMessages(prev => [...prev, {
      id: crypto.randomUUID(),
      role: 'bot',
      text,
      suggestions,
      intent,
      timestamp: new Date(),
    }])
    if (!open) setUnread(u => u + 1)
  }

  const addUserMessage = (text: string) => {
    setMessages(prev => [...prev, {
      id: crypto.randomUUID(),
      role: 'user',
      text,
      timestamp: new Date(),
    }])
  }

  const switchRole = (role: BotRole) => {
    setBotRole(role)
    setMessages([])
    setTimeout(() => {
      addBotMessage(role === 'admin' ? WELCOME_ADMIN : WELCOME_USER)
    }, 100)
  }

  const sendMessage = async (text: string) => {
    if (!text.trim()) return
    setInput('')
    addUserMessage(text)
    setLoading(true)

    try {
      const res = await axiosInstance.post('/api/v1/chat/message', {
        message: text,
        role: botRole,
        session_id: sessionId,
      })
      const data = res.data
      if (!sessionId) setSessionId(data.session_id)

      addBotMessage(data.reply, data.suggestions, data.intent)
    } catch (_) {
      addBotMessage("Sorry, I'm having trouble connecting. Please try again in a moment.")
    } finally {
      setLoading(false)
    }
  }

  const saveFeedback = async (rating: number) => {
    setFeedbackRating(rating)
    try {
      await axiosInstance.post('/api/v1/chat/feedback', {
        rating,
        comment: '',
        session_id: sessionId,
      })
    } catch (_) { /* ignore */ }
    addBotMessage(
      rating >= 4
        ? "Thank you for the great feedback! 🌟 Happy to help anytime."
        : "Thanks for the feedback. We'll use it to improve. Is there anything specific we can do better?"
    )
    setShowFeedback(false)
  }

  return (
    <>
      {/* Chat bubble */}
      <button
        onClick={() => setOpen(o => !o)}
        className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-indigo-600 text-white shadow-lg hover:bg-indigo-700 transition-all flex items-center justify-center"
        aria-label="Open chat"
      >
        {open ? (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        ) : (
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        )}
        {unread > 0 && !open && (
          <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-xs flex items-center justify-center">
            {unread}
          </span>
        )}
      </button>

      {/* Chat window */}
      {open && (
        <div className="fixed bottom-24 right-6 z-50 w-80 sm:w-96 h-[520px] bg-white rounded-2xl shadow-2xl flex flex-col border border-gray-200 overflow-hidden">

          {/* Header */}
          <div className="bg-indigo-600 px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center text-sm font-bold text-white">
                V
              </div>
              <div>
                <p className="text-white text-sm font-semibold">Vikas Assistant</p>
                <p className="text-indigo-200 text-xs">Always here to help</p>
              </div>
            </div>
            {/* Role switcher */}
            <div className="flex gap-1">
              <button
                onClick={() => switchRole('user')}
                className={`text-xs px-2 py-1 rounded-full transition-colors ${botRole === 'user' ? 'bg-white text-indigo-600' : 'text-white/70 hover:text-white'}`}
              >
                User
              </button>
              <button
                onClick={() => switchRole('admin')}
                className={`text-xs px-2 py-1 rounded-full transition-colors ${botRole === 'admin' ? 'bg-white text-indigo-600' : 'text-white/70 hover:text-white'}`}
              >
                Admin
              </button>
            </div>
          </div>

          {/* Pre-chat form */}
          {step === 'prechat' && (
            <div className="flex-1 overflow-y-auto p-5 bg-gray-50">
              <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
                <p className="text-sm font-semibold text-gray-800 mb-1">Before we start 👋</p>
                <p className="text-xs text-gray-500 mb-4">Please share your details so we can personalise your experience and follow up if needed.</p>

                <div className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-gray-600 block mb-1">Name *</label>
                    <input
                      type="text"
                      value={leadForm.name}
                      onChange={e => { setLeadForm(f => ({ ...f, name: e.target.value })); setPrechatErrors(er => ({ ...er, name: '' })) }}
                      placeholder="Your full name"
                      className={`w-full text-sm border rounded-lg px-3 py-2 outline-none focus:border-indigo-400 ${prechatErrors.name ? 'border-red-400' : 'border-gray-200'}`}
                    />
                    {prechatErrors.name && <p className="text-xs text-red-500 mt-0.5">{prechatErrors.name}</p>}
                  </div>

                  <div>
                    <label className="text-xs font-medium text-gray-600 block mb-1">Phone *</label>
                    <input
                      type="tel"
                      value={leadForm.phone}
                      onChange={e => { setLeadForm(f => ({ ...f, phone: e.target.value })); setPrechatErrors(er => ({ ...er, phone: '' })) }}
                      placeholder="+91 9876543210"
                      className={`w-full text-sm border rounded-lg px-3 py-2 outline-none focus:border-indigo-400 ${prechatErrors.phone ? 'border-red-400' : 'border-gray-200'}`}
                    />
                    {prechatErrors.phone && <p className="text-xs text-red-500 mt-0.5">{prechatErrors.phone}</p>}
                  </div>

                  <div>
                    <label className="text-xs font-medium text-gray-600 block mb-1">Email *</label>
                    <input
                      type="email"
                      value={leadForm.email}
                      onChange={e => { setLeadForm(f => ({ ...f, email: e.target.value })); setPrechatErrors(er => ({ ...er, email: '' })) }}
                      placeholder="you@company.com"
                      className={`w-full text-sm border rounded-lg px-3 py-2 outline-none focus:border-indigo-400 ${prechatErrors.email ? 'border-red-400' : 'border-gray-200'}`}
                    />
                    {prechatErrors.email && <p className="text-xs text-red-500 mt-0.5">{prechatErrors.email}</p>}
                  </div>

                  <div>
                    <label className="text-xs font-medium text-gray-600 block mb-1">Company (optional)</label>
                    <input
                      type="text"
                      value={leadForm.company || ''}
                      onChange={e => setLeadForm(f => ({ ...f, company: e.target.value }))}
                      placeholder="Your company name"
                      className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 outline-none focus:border-indigo-400"
                    />
                  </div>

                  <button
                    onClick={handlePrechatSubmit}
                    disabled={savingLead}
                    className="w-full bg-indigo-600 text-white text-sm font-medium rounded-lg py-2.5 hover:bg-indigo-700 disabled:opacity-50 transition-colors mt-2"
                  >
                    {savingLead ? 'Starting chat...' : 'Start Chat →'}
                  </button>

                  {botRole === 'admin' && (
                    <button
                      onClick={() => setStep('chat')}
                      className="w-full text-xs text-gray-400 hover:text-gray-600 text-center"
                    >
                      Skip (Admin access)
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Messages */}
          {step === 'chat' && (
          <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50">
            {messages.map(msg => (
              <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${
                  msg.role === 'user'
                    ? 'bg-indigo-600 text-white rounded-br-none'
                    : 'bg-white text-gray-800 shadow-sm border border-gray-100 rounded-bl-none'
                }`}>
                  <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>
                  {msg.suggestions && msg.suggestions.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {msg.suggestions.map((s, i) => (
                        <button
                          key={i}
                          onClick={() => sendMessage(s)}
                          className="text-xs bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-full px-2 py-0.5 hover:bg-indigo-100 transition-colors"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Topic bubbles — shown after welcome message, before user sends first message */}
            {messages.length === 1 && messages[0].role === 'bot' && botRole === 'user' && (
              <div className="flex flex-wrap gap-1.5 mt-1">
                {TOPIC_BUBBLES.map((topic, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(topic.label)}
                    className="flex items-center gap-1 text-xs bg-white border border-indigo-200 text-indigo-700 rounded-full px-3 py-1.5 hover:bg-indigo-50 transition-colors shadow-sm"
                  >
                    <span>{topic.icon}</span>
                    <span>{topic.label}</span>
                  </button>
                ))}
              </div>
            )}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-white border border-gray-100 shadow-sm rounded-2xl rounded-bl-none px-4 py-3">
                  <div className="flex gap-1">
                    <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
          )}

          {/* Feedback bar */}
          {showFeedback && (
            <div className="px-4 py-2 bg-yellow-50 border-t border-yellow-100 flex items-center justify-between">
              <span className="text-xs text-yellow-700">Was this helpful?</span>
              <div className="flex gap-1">
                {[1, 2, 3, 4, 5].map(r => (
                  <button
                    key={r}
                    onClick={() => saveFeedback(r)}
                    className={`text-lg transition-transform hover:scale-110 ${r <= feedbackRating ? 'text-yellow-400' : 'text-gray-300'}`}
                  >
                    ★
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Input — only shown in chat step */}
          {step === 'chat' && <div className="p-3 border-t bg-white flex gap-2">
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage(input)}
              placeholder={
                step === 'lead_name' ? 'Your name...' :
                step === 'lead_phone' ? 'Your phone number...' :
                step === 'lead_email' ? 'Your email...' :
                'Type a message...'
              }
              className="flex-1 text-sm border border-gray-200 rounded-full px-4 py-2 outline-none focus:border-indigo-400 transition-colors"
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={loading || !input.trim()}
              className="w-9 h-9 rounded-full bg-indigo-600 text-white flex items-center justify-center hover:bg-indigo-700 disabled:opacity-40 transition-colors"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>}

          {/* Footer */}
          <div className="px-4 pb-2 flex items-center justify-between">
            <p className="text-xs text-gray-400">Powered by Vikas AI</p>
            <button
              onClick={() => setShowFeedback(f => !f)}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              Rate this chat
            </button>
          </div>
        </div>
      )}
    </>
  )
}
