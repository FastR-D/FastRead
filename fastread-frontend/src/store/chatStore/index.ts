import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ChatSource } from '@/services/chat'

const CHAT_STORAGE_KEY = 'fastread-chat-storage'
const LEGACY_CHAT_STORAGE_KEY = 'bilinote-chat-storage'

if (typeof window !== 'undefined') {
  const legacyValue = localStorage.getItem(LEGACY_CHAT_STORAGE_KEY)
  if (legacyValue && !localStorage.getItem(CHAT_STORAGE_KEY)) {
    localStorage.setItem(CHAT_STORAGE_KEY, legacyValue)
  }
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
}

interface ChatState {
  chatHistory: Record<string, ChatMessage[]>
  addMessage: (taskId: string, msg: ChatMessage) => void
  clearChat: (taskId: string) => void
  getMessages: (taskId: string) => ChatMessage[]
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      chatHistory: {},

      addMessage: (taskId, msg) =>
        set(state => ({
          chatHistory: {
            ...state.chatHistory,
            [taskId]: [...(state.chatHistory[taskId] || []), msg],
          },
        })),

      clearChat: (taskId) =>
        set(state => {
          const nextHistory = { ...state.chatHistory }
          delete nextHistory[taskId]
          return { chatHistory: nextHistory }
        }),

      getMessages: (taskId) => get().chatHistory[taskId] || [],
    }),
    {
      name: CHAT_STORAGE_KEY,
    },
  ),
)
