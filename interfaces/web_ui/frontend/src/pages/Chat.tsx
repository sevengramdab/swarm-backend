import { useState } from 'react'
import { useChat } from '@/hooks/useChat'
import { useModels } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Slider } from '@/components/ui/slider'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Send, Plus, Trash2, Edit3, Loader2, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ChatMessage } from '@/types/index'

const MODES = ['agent', 'plan', 'research', 'swarm_code', 'debug', 'auto']

export function Chat() {
  const {
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
  } = useChat()

  const { data: models } = useModels()
  const [input, setInput] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')

  const handleSend = () => {
    if (!input.trim()) return
    sendMessage(input.trim())
    setInput('')
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] gap-4">
      {/* Conversation Sidebar */}
      <div className="flex w-64 flex-col gap-3 border-r pr-4">
        <Button onClick={createConversation} className="w-full">
          <Plus className="mr-2 h-4 w-4" />
          New Chat
        </Button>
        <ScrollArea className="flex-1">
          <div className="space-y-1">
            {conversations.map((conv) => (
              <div
                key={conv.id}
                className={cn(
                  'group flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-sm transition-colors',
                  activeId === conv.id ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
                )}
                onClick={() => {
                  setActiveId(conv.id)
                  setMode(conv.mode)
                }}
              >
                {editingId === conv.id ? (
                  <Input
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    onBlur={() => {
                      renameConversation(conv.id, editingName)
                      setEditingId(null)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        renameConversation(conv.id, editingName)
                        setEditingId(null)
                      }
                    }}
                    autoFocus
                    className="h-6 text-xs"
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <span className="flex-1 truncate">{conv.name}</span>
                )}
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-6 w-6"
                    onClick={(e) => {
                      e.stopPropagation()
                      setEditingId(conv.id)
                      setEditingName(conv.name)
                    }}
                  >
                    <Edit3 className="h-3 w-3" />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-6 w-6"
                    onClick={(e) => {
                      e.stopPropagation()
                      deleteConversation(conv.id)
                    }}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>

      {/* Chat Area */}
      <div className="flex flex-1 flex-col gap-4">
        {/* Mode Tabs */}
        <Tabs
          value={mode}
          onValueChange={(v) => {
            setMode(v)
            if (activeId) setConversationMode(activeId, v)
          }}
        >
          <TabsList>
            {MODES.map((m) => (
              <TabsTrigger key={m} value={m} className="text-xs capitalize">
                {m.replace('_', ' ')}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {/* Messages */}
        <ScrollArea className="flex-1 rounded-md border p-4">
          <div className="space-y-4">
            {activeConversation?.messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
            ))}
            {thinking && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Thinking...
              </div>
            )}
            {!activeConversation?.messages.length && !thinking && (
              <div className="flex h-full flex-col items-center justify-center text-muted-foreground">
                <MessageSquare className="mb-2 h-8 w-8 opacity-50" />
                <p>Select or start a conversation</p>
              </div>
            )}
          </div>
        </ScrollArea>

        {/* Controls */}
        <div className="flex items-center gap-3">
          <div className="w-40">
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger>
                <SelectValue placeholder="Model" />
              </SelectTrigger>
              <SelectContent>
                {models?.map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex w-48 flex-col gap-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Temperature</span>
              <span>{temperature.toFixed(2)}</span>
            </div>
            <Slider
              value={[temperature]}
              onValueChange={(v) => setTemperature(v[0])}
              min={0}
              max={2}
              step={0.01}
            />
          </div>
        </div>

        {/* Input */}
        <div className="flex gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message..."
            className="min-h-[60px] flex-1 resize-none"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
          />
          <Button onClick={handleSend} disabled={thinking || !input.trim()} className="self-end">
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[80%] rounded-lg px-4 py-2 text-sm',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground',
          message.error && 'border border-destructive text-destructive bg-transparent'
        )}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
      </div>
    </div>
  )
}
