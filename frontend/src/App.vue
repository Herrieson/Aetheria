<script setup>
import { computed, ref } from 'vue'
import { submitReview } from './services/reviewService'
import SampleShowcase from './components/SampleShowcase.vue'

const primaryInput = ref('')
const imageDataUrl = ref('')
const imageName = ref('')
const imageError = ref('')
const isDragActive = ref(false)
const fileInput = ref(null)

const views = [
  { key: 'review', label: '审核工作台' },
  { key: 'showcase', label: '样例展示' },
]

const activeView = ref(views[0].key)

const isLoading = ref(false)
const errorMessage = ref('')
const result = ref(null)

const MAX_IMAGE_SIZE_BYTES = 8 * 1024 * 1024

const isReviewView = computed(() => activeView.value === 'review')
const canSubmit = computed(() => primaryInput.value.trim().length > 0 && !isLoading.value)
const hasResponse = computed(() => Boolean(result.value))
const formDirty = computed(() => Boolean(primaryInput.value.trim() || imageDataUrl.value || result.value))

const metadataEntries = computed(() => {
  const metadata = result.value?.metadata
  if (!metadata) {
    return []
  }

  return Object.entries(metadata).reduce((accumulator, [key, value]) => {
    if (value === undefined || value === null) {
      return accumulator
    }

    if (typeof value === 'object') {
      accumulator.push({ key, value, isObject: true })
      return accumulator
    }

    const text = `${value}`.trim()
    if (text) {
      accumulator.push({ key, value: text, isObject: false })
    }
    return accumulator
  }, [])
})

const scoreLabel = computed(() => {
  if (!result.value) return '结果未知'

  const rawScore = result.value.predicted_score
  const numericScore = Number(rawScore)

  if (!Number.isNaN(numericScore)) {
    if (numericScore === 0) return '无风险'
    if (numericScore === 1) return '有风险'
  }

  if (rawScore === undefined || rawScore === null) {
    return '结果未知'
  }

  const text = String(rawScore).trim()
  return text || '结果未知'
})

const scoreTone = computed(() => {
  if (!result.value) return 'neutral'

  const score = Number(result.value.predicted_score)
  if (Number.isNaN(score)) return 'neutral'
  if (score === 0) return 'positive'
  if (score === 1) return 'negative'
  return 'neutral'
})

const formatScoreValue = (value) => {
  if (value === null || value === undefined) {
    return '—'
  }
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) {
    return '—'
  }
  return numberValue.toFixed(2)
}

const requestShortId = computed(() => {
  const id = result.value?.request_id
  if (typeof id === 'string' && id.trim()) {
    return id.slice(0, 8)
  }
  return '—'
})

const ragDetails = computed(() => result.value?.rag_details ?? null)

const ragOverview = computed(() => {
  const overview = ragDetails.value?.cases_overview
  if (typeof overview !== 'string') {
    return ''
  }
  return overview.trim()
})

const ragMeta = computed(() => {
  if (!ragDetails.value) return []
  const entries = [
    { label: '运行模式', value: ragDetails.value.runtime_mode || ragDetails.value.requested_mode },
    { label: '命中案例', value: ragDetails.value.num_cases },
    { label: '集合名称', value: ragDetails.value.collection_name },
    { label: 'Supporter 状态', value: ragDetails.value.supporter_llm_status },
  ]
  return entries.filter((entry) => entry.value !== undefined && entry.value !== null && entry.value !== '')
})

const panelVoteSourceLabel = computed(() => {
  if (!result.value?.panel_vote_source) return ''
  const map = {
    arbiter_final: 'Holistic Arbiter 裁决',
    panel_majority: '辩手面板多数票',
    single_debater: '单一辩手投票',
    panel_tie: '辩手投票平局',
    no_votes: '无可用投票',
  }
  return map[result.value.panel_vote_source] ?? result.value.panel_vote_source
})

const arbiterVoteLabel = computed(() => {
  const vote = result.value?.arbiter_vote
  if (vote === 1) return '有风险 (1)'
  if (vote === 0) return '无风险 (0)'
  return '未给出'
})

const weightedScoreText = computed(() => {
  const value = result.value?.weighted_score
  if (value === null || value === undefined) return '—'
  const numeric = Number(value)
  return Number.isNaN(numeric) ? '—' : numeric.toFixed(2)
})

const roundSeries = computed(() => {
  if (!result.value) return []
  const entries = []
  if (Array.isArray(result.value.strict_round_scores) && result.value.strict_round_scores.length) {
    const text = result.value.strict_round_scores
      .map((score, index) => `R${index + 1}: ${formatScoreValue(score)}`)
      .join(' · ')
    entries.push({ key: 'strict', label: 'Strict Debater', text })
  }
  if (Array.isArray(result.value.loose_round_scores) && result.value.loose_round_scores.length) {
    const text = result.value.loose_round_scores
      .map((score, index) => `R${index + 1}: ${formatScoreValue(score)}`)
      .join(' · ')
    entries.push({ key: 'loose', label: 'Loose Debater', text })
  }
  return entries
})

const majorityLabel = computed(() => {
  const details = result.value?.majority_vote
  if (!details) return ''
  if (details.tie) return '投票结果：平局'
  if (details.majority === 1) return '投票结果：有风险'
  if (details.majority === 0) return '投票结果：无风险'
  return ''
})

const majorityMeta = computed(() => {
  const details = result.value?.majority_vote
  if (!details) return ''
  const total = details.total_votes
  if (typeof total === 'number') {
    return `总票数：${total}`
  }
  return ''
})

const hasPanelInsights = computed(() => {
  if (!result.value) return false
  const {
    panel_vote_source: panelVoteSource,
    strict_score: strictScore,
    loose_score: looseScore,
    strict_round_scores: strictRounds,
    loose_round_scores: looseRounds,
    weighted_score: weightedScore,
    arbiter_vote: arbiterVote,
    majority_vote: majorityVote,
    threshold_note: thresholdNote,
  } = result.value

  return Boolean(
    panelVoteSource ||
      (strictScore !== undefined && strictScore !== null) ||
      (looseScore !== undefined && looseScore !== null) ||
      (Array.isArray(strictRounds) && strictRounds.length) ||
      (Array.isArray(looseRounds) && looseRounds.length) ||
      (weightedScore !== undefined && weightedScore !== null) ||
      (arbiterVote !== undefined && arbiterVote !== null) ||
      majorityVote ||
      thresholdNote
  )
})

const formatTimestamp = (timestamp) => {
  if (!timestamp) return 'Unknown time'
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return timestamp
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

const clearImage = ({ keepError = false } = {}) => {
  imageDataUrl.value = ''
  imageName.value = ''
  if (!keepError) {
    imageError.value = ''
  }
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

const readFileAsDataUrl = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error('无法读取图片文件。'))
    reader.readAsDataURL(file)
  })

const stripMetadataWithCanvas = async (file) => {
  const dataUrl = await readFileAsDataUrl(file)

  return new Promise((resolve, reject) => {
    if (typeof dataUrl !== 'string') {
      reject(new Error('无效的图片数据。'))
      return
    }

    const image = new Image()
    image.crossOrigin = 'anonymous'
    image.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = image.naturalWidth || image.width
      canvas.height = image.naturalHeight || image.height

      const context = canvas.getContext('2d')
      if (!context) {
        reject(new Error('浏览器不支持图像处理。'))
        return
      }

      context.drawImage(image, 0, 0)
      const mimeType = file.type && file.type.startsWith('image/') ? file.type : 'image/png'
      const quality = mimeType === 'image/jpeg' ? 0.92 : undefined
      resolve(canvas.toDataURL(mimeType, quality))
    }
    image.onerror = () => reject(new Error('无法解析图片内容。'))
    image.src = dataUrl
  })
}

const sanitiseImage = async (file) => {
  try {
    return await stripMetadataWithCanvas(file)
  } catch (error) {
    console.warn('IMAGE_SANITISE_FALLBACK', error)
    return readFileAsDataUrl(file)
  }
}

const processFile = async (file) => {
  imageError.value = ''

  if (!file.type.startsWith('image/')) {
    clearImage({ keepError: true })
    imageError.value = '仅支持图片文件。'
    return
  }

  if (file.size > MAX_IMAGE_SIZE_BYTES) {
    clearImage({ keepError: true })
    imageError.value = '图片大小需小于 8 MB。'
    return
  }

  try {
    const sanitized = await sanitiseImage(file)
    if (typeof sanitized !== 'string') {
      throw new Error('无法生成图片数据。')
    }
    imageDataUrl.value = sanitized
    imageName.value = file.name
    imageError.value = ''
    if (fileInput.value) {
      fileInput.value.value = ''
    }
  } catch (error) {
    clearImage({ keepError: true })
    imageError.value =
      error instanceof Error && error.message ? error.message : '图片处理失败，请重试。'
  }
}

const handleFileSelect = async (event) => {
  const files = event.target?.files
  if (files?.length) {
    await processFile(files[0])
  }
}

const handleDrop = async (event) => {
  const files = event.dataTransfer?.files
  if (files?.length) {
    await processFile(files[0])
  }
  isDragActive.value = false
}

const handleDragEnter = (event) => {
  event.preventDefault()
  isDragActive.value = true
}

const handleDragOver = (event) => {
  event.preventDefault()
  isDragActive.value = true
}

const handleDragLeave = (event) => {
  event.preventDefault()
  if (event.currentTarget?.contains(event.relatedTarget)) {
    return
  }
  isDragActive.value = false
}

const openFilePicker = () => {
  fileInput.value?.click()
}

const removeImage = () => {
  clearImage()
}

const handleReset = () => {
  if (isLoading.value) return
  primaryInput.value = ''
  clearImage()
  errorMessage.value = ''
  result.value = null
}

const switchView = (viewKey) => {
  activeView.value = viewKey
}

const handleSubmit = async () => {
  if (!canSubmit.value) return

  isLoading.value = true
  errorMessage.value = ''

  try {
    const metadata = {
      source: 'frontend',
    }

    if (imageDataUrl.value) {
      metadata.image = {
        filename: imageName.value,
        sanitised: true,
      }
    }

    const payload = {
      input_1: primaryInput.value.trim(),
      input_2: imageDataUrl.value || '',
      metadata,
    }

    const response = await submitReview(payload)
    result.value = response
  } catch (error) {
    errorMessage.value =
      error instanceof Error && error.message ? error.message : '无法提交审核请求，请稍后再试。'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="page">
    <header class="topbar">
      <span class="topbar-brand">Aetheria</span>
      <nav class="topbar-nav" aria-label="页面切换">
        <button
          v-for="view in views"
          :key="view.key"
          type="button"
          class="nav-button"
          :class="{ active: activeView === view.key }"
          @click="switchView(view.key)"
        >
          {{ view.label }}
        </button>
      </nav>
    </header>

    <div v-if="isReviewView" class="view view--review">
      <section class="hero">
        <span class="badge">Aetheria</span>
        <h1>Aetheria 内容审核工作台</h1>
        <p>
          将内容提交给 Aetheria 多智能体评审服务，快速获取风险评分、模型推理与完整对话轨迹。
        </p>
      </section>

      <form class="panel panel--form" @submit.prevent="handleSubmit" novalidate>
        <div class="panel-header">
          <div>
            <h2>创建审核任务</h2>
            <p>主内容为必填项，可选上传图片，系统会自动生成文字描述。</p>
          </div>
        </div>

        <div class="form-grid">
          <label class="field field--primary">
            <span class="field-label">
              主内容
              <span class="required">*</span>
            </span>
            <textarea
              v-model="primaryInput"
              rows="6"
              placeholder="粘贴或输入需要分析的文本内容……"
              required
            ></textarea>
          </label>

          <div class="field field--upload">
            <span class="field-label">图片上传（可选）</span>
            <div
              class="dropzone"
              :class="{
                'is-active': isDragActive,
                'has-image': Boolean(imageDataUrl),
              }"
              @dragenter.prevent="handleDragEnter"
              @dragover.prevent="handleDragOver"
              @dragleave="handleDragLeave"
              @drop.prevent="handleDrop"
              @click="openFilePicker"
            >
              <input
                ref="fileInput"
                type="file"
                accept="image/*"
                class="file-input"
                @change="handleFileSelect"
              />

              <template v-if="imageDataUrl">
                <img :src="imageDataUrl" :alt="imageName || '已选择的图片'" class="preview-image" />
                <div class="preview-meta">
                  <span class="filename" :title="imageName">{{ imageName || '已选择的图片' }}</span>
                  <button type="button" class="remove" @click.stop="removeImage">移除图片</button>
                </div>
              </template>

              <template v-else>
                <div class="placeholder">
                  <span class="icon" aria-hidden="true">🖼️</span>
                  <p>拖拽图片到此处，或<span class="link">点击上传</span></p>
                  <p class="hint">支持 JPG、PNG、WebP 等格式，上传后自动去除元数据。</p>
                </div>
              </template>
            </div>

            <p v-if="imageError" class="field-error" role="alert">{{ imageError }}</p>
          </div>
        </div>

        <div class="form-actions">
          <button type="submit" :disabled="!canSubmit">
            <span v-if="isLoading" class="spinner" aria-hidden="true"></span>
            {{ isLoading ? '提交中…' : '提交审核' }}
          </button>
          <button type="button" class="ghost" @click="handleReset" :disabled="!formDirty">
            清空
          </button>
        </div>

        <p v-if="errorMessage" class="form-error" role="alert">
          {{ errorMessage }}
        </p>
      </form>

      <transition name="fade">
        <section v-if="hasResponse" class="panel panel--result" aria-live="polite">
          <header class="result-header">
            <div>
              <span class="eyebrow">请求 ID · {{ requestShortId }}</span>
              <h2>审核结果</h2>
              <p class="timestamp">完成时间：{{ formatTimestamp(result.created_at) }}</p>
            </div>
            <div :class="['score-pill', scoreTone]">
              <span>审核结论</span>
              <strong>{{ scoreLabel }}</strong>
            </div>
          </header>

          <div class="result-grid">
            <article class="card">
              <h3>模型推理</h3>
              <p>{{ result.reasoning }}</p>
            </article>

            <article class="card">
              <h3>背景信息</h3>
              <p>{{ result.background_info }}</p>
            </article>

            <article v-if="hasPanelInsights" class="card insights-card">
              <h3>裁决结构</h3>
              <ul class="stat-list">
                <li v-if="panelVoteSourceLabel">
                  <span>最终依据</span>
                  <strong>{{ panelVoteSourceLabel }}</strong>
                  <p v-if="result.threshold_note" class="stat-subtext">{{ result.threshold_note }}</p>
                </li>
                <li v-if="result.strict_score !== undefined && result.strict_score !== null">
                  <span>Strict Debater</span>
                  <strong>{{ formatScoreValue(result.strict_score) }}</strong>
                </li>
                <li v-if="result.loose_score !== undefined && result.loose_score !== null">
                  <span>Loose Debater</span>
                  <strong>{{ formatScoreValue(result.loose_score) }}</strong>
                </li>
                <li v-if="weightedScoreText !== '—'">
                  <span>加权得分</span>
                  <strong>{{ weightedScoreText }}</strong>
                </li>
                <li>
                  <span>Holistic Arbiter</span>
                  <strong>{{ arbiterVoteLabel }}</strong>
                </li>
                <li v-if="majorityLabel">
                  <span>面板投票</span>
                  <strong>{{ majorityLabel }}</strong>
                  <p v-if="majorityMeta" class="stat-subtext">{{ majorityMeta }}</p>
                </li>
                <li v-for="series in roundSeries" :key="series.key" class="history-line">
                  <span>{{ series.label }} 轮次轨迹</span>
                  <p>{{ series.text }}</p>
                </li>
              </ul>
            </article>

            <article v-if="ragOverview || ragMeta.length" class="card full rag-card">
              <h3>检索上下文</h3>
              <div v-if="ragMeta.length" class="rag-meta">
                <span v-for="entry in ragMeta" :key="entry.label">
                  {{ entry.label }}：{{ entry.value }}
                </span>
              </div>
              <pre v-if="ragOverview">{{ ragOverview }}</pre>
              <p v-else class="rag-empty">Supporter 未返回案例摘要。</p>
            </article>

            <article class="card full">
              <h3>对话轨迹</h3>
              <ul class="messages">
                <li v-for="(message, index) in result.messages" :key="`${message.role}-${index}`">
                  <span class="role">{{ message.role }}</span>
                  <p>{{ message.content }}</p>
                </li>
              </ul>
            </article>

            <article v-if="metadataEntries.length" class="card metadata">
              <h3>记录的元数据</h3>
              <ul>
                <li v-for="entry in metadataEntries" :key="entry.key">
                  <span>{{ entry.key }}</span>
                  <pre v-if="entry.isObject">{{ JSON.stringify(entry.value, null, 2) }}</pre>
                  <p v-else>{{ entry.value }}</p>
                </li>
              </ul>
            </article>
          </div>

          <footer class="result-footer">
            <span>日志文件路径：</span>
            <code>{{ result.log_path }}</code>
          </footer>
        </section>
      </transition>
    </div>

    <div v-else class="view view--showcase">
      <SampleShowcase />
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 2.5rem;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.85);
  box-shadow: 0 12px 28px -18px rgba(38, 44, 80, 0.25);
  border: 1px solid rgba(186, 198, 238, 0.4);
  backdrop-filter: blur(8px);
}

.topbar-brand {
  font-size: 1.05rem;
  font-weight: 700;
  color: #1a2142;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.topbar-nav {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
}

.nav-button {
  border: none;
  border-radius: 999px;
  padding: 0.55rem 1.4rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: #3a4572;
  background: rgba(76, 110, 255, 0.12);
  cursor: pointer;
  transition: background 0.2s ease, transform 0.15s ease, color 0.2s ease;
}

.nav-button:hover {
  transform: translateY(-1px);
  background: rgba(76, 110, 255, 0.2);
}

.nav-button.active {
  color: #ffffff;
  background: linear-gradient(135deg, #5064ff, #27b5ff);
  box-shadow: 0 10px 24px -14px rgba(76, 110, 255, 0.6);
}

.view {
  display: flex;
  flex-direction: column;
  gap: 2.5rem;
}

.view--showcase {
  gap: 2rem;
}

@media (max-width: 620px) {
  .topbar {
    flex-direction: column;
    align-items: stretch;
    gap: 0.75rem;
  }

  .topbar-nav {
    justify-content: space-between;
  }

  .nav-button {
    flex: 1;
    text-align: center;
  }
}

.hero {
  padding: 2.5rem;
  border-radius: 24px;
  background: linear-gradient(135deg, rgba(74, 58, 255, 0.12), rgba(30, 200, 252, 0.18));
  backdrop-filter: blur(6px);
  text-align: center;
  box-shadow: 0 24px 48px -24px rgba(40, 46, 70, 0.4);
  color: #0c0f2b;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.875rem;
  font-weight: 600;
  padding: 0.4rem 0.75rem;
  border-radius: 999px;
  background: rgba(46, 125, 255, 0.12);
  color: #1c48d6;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 1rem;
}

.hero h1 {
  font-size: clamp(2rem, 3vw, 2.75rem);
  font-weight: 700;
  margin-bottom: 0.75rem;
}

.hero p {
  max-width: 48rem;
  margin: 0 auto;
  color: rgba(12, 15, 43, 0.8);
  font-size: 1.05rem;
}

.panel {
  padding: 2.25rem;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.95);
  box-shadow:
    0 14px 40px -18px rgba(28, 35, 70, 0.3),
    0 4px 18px -12px rgba(28, 35, 70, 0.15);
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

.panel--form {
  border: 1px solid rgba(188, 201, 236, 0.4);
}

.panel-header h2 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #122044;
}

.panel-header p {
  margin-top: 0.35rem;
  color: #5f6785;
}

.form-grid {
  display: grid;
  gap: 1.25rem;
}

@media (min-width: 768px) {
  .form-grid {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.field-label {
  font-weight: 600;
  color: #1a2142;
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.required {
  color: #ff5c5c;
  font-size: 0.825rem;
}

textarea,
input[type='text'] {
  width: 100%;
  border-radius: 16px;
  border: 1px solid rgba(123, 138, 182, 0.3);
  padding: 0.85rem 1rem;
  font-size: 1rem;
  line-height: 1.5;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  resize: vertical;
  background-color: rgba(255, 255, 255, 0.92);
}

textarea:focus,
input[type='text']:focus {
  outline: none;
  border-color: rgba(76, 110, 255, 0.7);
  box-shadow: 0 0 0 3px rgba(76, 110, 255, 0.18);
}

.field--upload {
  min-height: 100%;
}

.dropzone {
  position: relative;
  border: 2px dashed rgba(76, 110, 255, 0.3);
  border-radius: 20px;
  background: rgba(244, 247, 255, 0.6);
  padding: 1.75rem 1.5rem;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  align-items: center;
  justify-content: center;
}

.field--upload .dropzone {
  min-height: 260px;
}

.dropzone.is-active {
  border-color: rgba(76, 110, 255, 0.7);
  background: rgba(244, 247, 255, 0.9);
  box-shadow: 0 0 0 3px rgba(76, 110, 255, 0.18);
}

.dropzone.has-image {
  background: rgba(244, 247, 255, 0.92);
  border-style: solid;
}

.file-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  pointer-events: none;
}

.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
  color: #4c5680;
  font-size: 0.95rem;
}

.placeholder .icon {
  font-size: 2rem;
}

.placeholder .link {
  margin-left: 0.35rem;
  color: #3b5bfd;
  text-decoration: underline;
}

.placeholder .hint {
  font-size: 0.85rem;
  color: #6b7394;
}

.preview-image {
  max-width: 100%;
  max-height: 220px;
  border-radius: 16px;
  object-fit: cover;
  box-shadow: 0 12px 28px -20px rgba(28, 35, 70, 0.4);
}

.preview-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  color: #39446e;
  font-size: 0.95rem;
}

.preview-meta .filename {
  max-width: 16rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-meta .remove {
  border: none;
  border-radius: 999px;
  padding: 0.4rem 0.9rem;
  background: rgba(255, 92, 92, 0.15);
  color: #b71c1c;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.15s ease;
}

.preview-meta .remove:hover {
  background: rgba(255, 92, 92, 0.25);
  transform: translateY(-1px);
}

.field-error {
  margin-top: 0.75rem;
  color: #c62828;
  background: rgba(255, 92, 92, 0.12);
  border: 1px solid rgba(255, 92, 92, 0.22);
  border-radius: 14px;
  padding: 0.6rem 0.9rem;
  font-size: 0.9rem;
}

.form-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.form-actions button {
  border: none;
  border-radius: 999px;
  padding: 0.85rem 1.75rem;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.2s ease, background 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
}

.form-actions button[disabled] {
  cursor: not-allowed;
  opacity: 0.55;
  transform: none;
  box-shadow: none;
}

.form-actions button:first-of-type {
  background: linear-gradient(135deg, #4460ff, #3ad0ff);
  color: white;
  box-shadow: 0 12px 24px -12px rgba(65, 92, 255, 0.6);
}

.form-actions button:first-of-type:not([disabled]):hover {
  transform: translateY(-1px);
  box-shadow: 0 16px 28px -16px rgba(65, 92, 255, 0.55);
}

.form-actions .ghost {
  background: rgba(255, 255, 255, 0.8);
  color: #3b4b82;
  border: 1px solid rgba(123, 138, 182, 0.35);
}

.form-actions .ghost:not([disabled]):hover {
  background: rgba(231, 236, 255, 0.88);
}

.spinner {
  width: 1.05rem;
  height: 1.05rem;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.7);
  border-top-color: rgba(255, 255, 255, 0.2);
  animation: spin 0.7s linear infinite;
}

.form-error {
  background: rgba(255, 92, 92, 0.12);
  color: #c62828;
  border-radius: 16px;
  padding: 0.75rem 1rem;
  border: 1px solid rgba(255, 92, 92, 0.25);
}

.panel--result {
  border: 1px solid rgba(67, 107, 255, 0.2);
  background: rgba(248, 250, 255, 0.95);
  gap: 2rem;
}

.result-header {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

@media (min-width: 768px) {
  .result-header {
    flex-direction: row;
    justify-content: space-between;
    align-items: flex-start;
  }
}

.eyebrow {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #6b75a1;
}

.timestamp {
  color: #6b75a1;
  margin-top: 0.35rem;
}

.score-pill {
  align-self: flex-start;
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.4rem;
  padding: 0.85rem 1.1rem;
  border-radius: 18px;
  background: rgba(66, 87, 255, 0.12);
  color: #2d3b8d;
  font-size: 0.95rem;
  font-weight: 600;
  min-width: 8rem;
}

.score-pill strong {
  font-size: 1.6rem;
  font-weight: 700;
}

.score-pill.positive {
  background: rgba(64, 214, 146, 0.15);
  color: #0d7c55;
}

.score-pill.caution {
  background: rgba(255, 199, 67, 0.18);
  color: #9f6700;
}

.score-pill.negative {
  background: rgba(255, 92, 92, 0.18);
  color: #b22929;
}

.result-grid {
  display: grid;
  gap: 1.5rem;
}

.stat-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.stat-list span {
  font-size: 0.92rem;
  color: #5a628c;
  font-weight: 600;
}

.stat-list strong {
  display: block;
  font-size: 1.1rem;
  color: #11163c;
}

.stat-subtext {
  margin-top: 0.25rem;
  font-size: 0.85rem;
  color: #6b7394;
}

.history-line p {
  margin-top: 0.35rem;
  color: #2f3658;
  font-size: 0.9rem;
}

.rag-card pre {
  margin-top: 1rem;
  background: rgba(16, 23, 61, 0.04);
  border-radius: 16px;
  padding: 1rem;
  font-size: 0.9rem;
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.rag-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  font-size: 0.9rem;
  color: #3b4372;
}

.rag-meta span {
  background: rgba(76, 110, 255, 0.1);
  padding: 0.4rem 0.85rem;
  border-radius: 999px;
}

.rag-empty {
  color: #6b7394;
  font-style: italic;
}

.card {
  background: white;
  border-radius: 20px;
  padding: 1.5rem;
  box-shadow: 0 12px 28px -24px rgba(27, 36, 84, 0.45);
  border: 1px solid rgba(210, 220, 255, 0.5);
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.card h3 {
  font-size: 1.1rem;
  font-weight: 700;
  color: #1c2554;
}

.card p {
  white-space: pre-wrap;
  color: #2f365a;
}

.card.full {
  grid-column: 1 / -1;
}

.messages {
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
  list-style: none;
  padding: 0;
}

.messages li {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  background: rgba(241, 244, 255, 0.8);
  border-radius: 16px;
  padding: 0.95rem 1.1rem;
  border: 1px solid rgba(199, 208, 255, 0.5);
}

.messages .role {
  font-size: 0.85rem;
  font-weight: 600;
  color: #4a5acf;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.metadata ul {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.metadata li {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 1rem;
  align-items: baseline;
}

.metadata span {
  font-weight: 600;
  color: #2a3170;
}

.metadata p {
  color: #4e568a;
  word-break: break-word;
}

.metadata pre {
  margin: 0;
  color: #4e568a;
  background: rgba(14, 20, 44, 0.06);
  padding: 0.65rem 0.75rem;
  border-radius: 12px;
  overflow: auto;
  max-height: 12rem;
  font-family: 'Fira Code', 'SFMono-Regular', Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 0.85rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.result-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  color: #4a5390;
  font-size: 0.95rem;
}

.result-footer code {
  background: rgba(14, 20, 44, 0.08);
  padding: 0.45rem 0.65rem;
  border-radius: 8px;
  font-family: 'Fira Code', 'SFMono-Regular', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }

  100% {
    transform: rotate(360deg);
  }
}

@media (min-width: 900px) {
  .form-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .field:nth-child(3) {
    grid-column: 1 / -1;
  }

  .result-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
