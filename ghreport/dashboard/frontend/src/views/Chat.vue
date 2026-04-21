<template>
  <div class="chat-page">
    <h2>Data Chat</h2>
    <p class="hint-text">Ask questions about your repository data in plain English.</p>

    <div class="chat-messages" ref="messagesEl">
      <div v-for="(msg, i) in messages" :key="i" :class="['chat-msg', msg.role]">
        <div class="msg-role">{{ msg.role === 'user' ? 'You' : 'Assistant' }}</div>
        <div class="msg-body" v-html="renderMd(msg.content)"></div>
        <div v-if="msg.steps && msg.steps.length" class="msg-steps">
          <details v-for="(step, j) in msg.steps" :key="j" class="step-details">
            <summary>
              <span class="step-badge">SQL query</span>
              {{ step.row_count != null ? `${step.row_count} rows` : '' }}
              {{ step.error ? '⚠ error' : '' }}
            </summary>
            <pre class="step-sql">{{ step.sql }}</pre>
            <div v-if="step.error" class="step-error">{{ step.error }}</div>
            <table v-else-if="step.rows && step.rows.length" class="step-table">
              <thead>
                <tr><th v-for="col in Object.keys(step.rows[0])" :key="col">{{ col }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in step.rows.slice(0, 20)" :key="ri">
                  <td v-for="col in Object.keys(step.rows[0])" :key="col">{{ row[col] }}</td>
                </tr>
              </tbody>
            </table>
            <p v-if="step.rows && step.rows.length > 20" class="step-truncated">
              Showing 20 of {{ step.rows.length }} rows
            </p>
          </details>
        </div>
      </div>
      <div v-if="loading" class="chat-msg assistant">
        <div class="msg-role">Assistant</div>
        <div class="msg-body loading-indicator">
          <span class="spinner">↻</span> {{ statusText }}
        </div>
      </div>
    </div>

    <form class="chat-input" @submit.prevent="send">
      <input
        v-model="input"
        placeholder="e.g. Which repos have the most stale open issues?"
        :disabled="loading"
        autofocus
      />
      <button class="primary" type="submit" :disabled="loading || !input.trim()">Send</button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import axios from 'axios'

interface Step {
  sql: string
  rows?: Record<string, unknown>[]
  row_count?: number
  error?: string
  truncated?: boolean
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  steps?: Step[]
}

const messages = ref<Message[]>([])
const input = ref('')
const loading = ref(false)
const statusText = ref('Thinking...')
const messagesEl = ref<HTMLElement | null>(null)

function renderMd(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^[-•] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/<\/ul>\s*<ul>/g, '')
    .replace(/\n/g, '<br>')
}

function scrollBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

async function send() {
  const text = input.value.trim()
  if (!text) return

  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true
  statusText.value = 'Thinking...'
  scrollBottom()

  try {
    // Build history from previous messages (exclude steps)
    const history = messages.value.slice(0, -1).map(m => ({
      role: m.role,
      content: m.content,
    }))

    const { data } = await axios.post('/api/chat', {
      message: text,
      history,
    })

    messages.value.push({
      role: 'assistant',
      content: data.answer || 'No response.',
      steps: data.steps || [],
    })
  } catch (e: any) {
    const detail = e.response?.data?.detail || 'Failed to get response'
    messages.value.push({ role: 'assistant', content: `Error: ${detail}` })
  } finally {
    loading.value = false
    scrollBottom()
  }
}
</script>

<style scoped>
.chat-page {
  max-width: 900px;
  margin: 0 auto;
}
.hint-text {
  color: #586069;
  font-style: italic;
  margin-bottom: 1rem;
}
.chat-messages {
  border: 1px solid #e1e4e8;
  border-radius: 6px;
  padding: 1rem;
  max-height: 60vh;
  overflow-y: auto;
  margin-bottom: 1rem;
  background: #fafbfc;
}
.chat-msg {
  margin-bottom: 1rem;
}
.chat-msg:last-child { margin-bottom: 0; }
.chat-msg.user .msg-role { color: #0366d6; font-weight: 600; }
.chat-msg.assistant .msg-role { color: #2ea44f; font-weight: 600; }
.msg-role { font-size: 0.8rem; margin-bottom: 0.2rem; }
.msg-body {
  background: #fff;
  border: 1px solid #e1e4e8;
  border-radius: 6px;
  padding: 0.6rem 0.8rem;
  line-height: 1.5;
  font-size: 0.9rem;
}
.chat-msg.user .msg-body { background: #f0f6ff; border-color: #c8d9f0; }
.msg-body :deep(ul) { margin: 0.3rem 0; padding-left: 1.2rem; }
.msg-body :deep(li) { margin-bottom: 0.2rem; }
.msg-body :deep(code) { background: #eef; padding: 0.1em 0.3em; border-radius: 3px; font-size: 0.85em; }

.msg-steps { margin-top: 0.5rem; }
.step-details {
  border: 1px solid #e1e4e8;
  border-radius: 4px;
  margin-bottom: 0.4rem;
  background: #fff;
}
.step-details summary {
  cursor: pointer;
  padding: 0.4rem 0.6rem;
  font-size: 0.8rem;
  color: #586069;
  user-select: none;
}
.step-badge {
  background: #e8ecf0;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-right: 0.3rem;
}
.step-sql {
  margin: 0;
  padding: 0.5rem 0.6rem;
  background: #f6f8fa;
  font-size: 0.8rem;
  overflow-x: auto;
  border-top: 1px solid #e1e4e8;
}
.step-error { color: #cb2431; padding: 0.4rem 0.6rem; font-size: 0.8rem; }
.step-table {
  width: 100%;
  font-size: 0.78rem;
  border-collapse: collapse;
  border-top: 1px solid #e1e4e8;
}
.step-table th, .step-table td {
  padding: 0.25rem 0.5rem;
  border-bottom: 1px solid #eee;
  text-align: left;
  white-space: nowrap;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.step-table th { background: #f6f8fa; font-weight: 600; }
.step-truncated { font-size: 0.75rem; color: #586069; padding: 0.3rem 0.6rem; margin: 0; }

.loading-indicator { color: #586069; }
.spinner { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.chat-input {
  display: flex;
  gap: 0.5rem;
}
.chat-input input {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid #e1e4e8;
  border-radius: 6px;
  font-size: 0.9rem;
}
.chat-input input:focus { outline: none; border-color: #0366d6; box-shadow: 0 0 0 2px rgba(3,102,214,0.2); }
</style>
