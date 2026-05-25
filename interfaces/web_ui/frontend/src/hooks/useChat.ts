import { useState, useCallback, useEffect } from 'react'
import type { Conversation, ChatMessage } from '@/types/index'
import { useInfer, pollChatTaskResult } from '@/hooks/useApi'

const STORAGE_KEY = 'simplepod_conversations_v2'

const MODE_PROMPTS: Record<string, string> = {
  agent: 'You are a helpful, concise AI assistant.',
  plan: 'You are a planning assistant. Break down tasks into clear, numbered steps.',
  research: 'You are a research assistant. Provide thorough, well-structured answers.',
  swarm_code: 'You are an expert software engineer. Write clean, production-ready code.',
  debug: 'You are a debugging expert. Analyze problems systematically.',
  auto: 'You are a versatile AI assistant. Adapt your response style.',
}

function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    // ignore
  }
  return []
}

function saveConversations(conversations: Conversation[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations))
}

export function useChat() {
  const [conversations, setConversations] = useState<Conversation[]>(loadConversations)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [mode, setMode] = useState<string>('agent')
  const [temperature, setTemperature] = useState<number>(0.7)
  const [model, setModel] = useState<string>('llama3.2')
  const [thinking, setThinking] = useState(false)
  const infer = useInfer()

  const activeConversation = conversations.find((c) => c.id === activeId) || null

  // Auto-select first conversation on load if none selected
  useEffect(() => {
    if (!activeId && conversations.length > 0) {
      setActiveId(conversations[0].id)
      setMode(conversations[0].mode)
    }
  }, [activeId, conversations])

  useEffect(() => {
    saveConversations(conversations)
  }, [conversations])

  const createConversation = useCallback(() => {
    const id = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`
    const conv: Conversation = {
      id,
      name: `Chat ${conversations.length + 1}`,
      mode: mode,
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    }
    setConversations((prev) => [...prev, conv])
    setActiveId(id)
  }, [conversations.length, mode])

  const renameConversation = useCallback((id: string, name: string) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, name, updatedAt: Date.now() } : c))
    )
  }, [])

  const deleteConversation = useCallback((id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id))
    setActiveId((curr) => (curr === id ? null : curr))
  }, [])

  const setConversationMode = useCallback((id: string, newMode: string) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, mode: newMode, updatedAt: Date.now() } : c))
    )
    if (activeId === id) setMode(newMode)
  }, [activeId])

  const sendMessage = useCallback(
    async (content: string) => {
      if (!activeId) return
      const conv = conversations.find((c) => c.id === activeId)
      if (!conv) return

      const userMsg: ChatMessage = { role: 'user', content }
      const messages = [...conv.messages, userMsg]
      setConversations((prev) =>
        prev.map((c) => (c.id === activeId ? { ...c, messages, updatedAt: Date.now() } : c))
      )

      setThinking(true)
      try {
        const prompt = MODE_PROMPTS[conv.mode] || MODE_PROMPTS.agent
        const result = await infer.mutateAsync({
          prompt: `${prompt}\n\n${content}`,
          model_hint: model || undefined,
          temperature,
          messages: messages.map((m) => ({ role: m.role, content: m.content })),
          mode: conv.mode,
        })

        if (result && 'task_id' in result && result.task_id) {
          const taskResult = (await pollChatTaskResult(result.task_id)) as {
            status: string
            result?: string
            error?: string
          }

          if (taskResult.error || taskResult.status === 'failed') {
            const errorMsg = taskResult.error || 'Task failed'
            const isMemoryError = errorMsg.toLowerCase().includes('model requires more system memory')
            const assistantMsg: ChatMessage = {
              role: 'assistant',
              content: isMemoryError
                ? 'This model requires more system memory than available. Try using a smaller model or closing other applications.'
                : errorMsg,
              error: true,
            }
            setConversations((prev) =>
              prev.map((c) => (c.id === activeId ? { ...c, messages: [...c.messages, assistantMsg], updatedAt: Date.now() } : c))
            )
          } else {
            // result can be an object {response, model, ...} or a raw string
            const rawResult = taskResult.result as any
            const responseText = typeof rawResult === 'string'
              ? rawResult
              : rawResult?.response || rawResult?.result || JSON.stringify(rawResult) || ''
            const assistantMsg: ChatMessage = {
              role: 'assistant',
              content: responseText,
            }
            setConversations((prev) =>
              prev.map((c) => (c.id === activeId ? { ...c, messages: [...c.messages, assistantMsg], updatedAt: Date.now() } : c))
            )
          }
        } else {
          throw new Error('No task ID returned')
        }
      } catch (e) {
        const errorMsg = e instanceof Error ? e.message : 'Unknown error'
        const isMemoryError = errorMsg.toLowerCase().includes('model requires more system memory')
        const assistantMsg: ChatMessage = {
          role: 'assistant',
          content: isMemoryError
            ? 'This model requires more system memory than available. Try using a smaller model or closing other applications.'
            : errorMsg,
          error: true,
        }
        setConversations((prev) =>
          prev.map((c) => (c.id === activeId ? { ...c, messages: [...c.messages, assistantMsg], updatedAt: Date.now() } : c))
        )
      } finally {
        setThinking(false)
      }
    },
    [activeId, conversations, infer, model, temperature]
  )

  return {
    conversations,
    activeId,
    activeConversation,
    mode,
    temperature,
    model,
    thinking,
    setActiveId,
    setMode,
    setTemperature,
    setModel,
    createConversation,
    renameConversation,
    deleteConversation,
    setConversationMode,
    sendMessage,
  }
}
