<script setup>
import { computed, ref } from 'vue'
import { defaultGroupKey, sampleGroups } from '@/data/sampleShowcase'

const selectedKey = ref(defaultGroupKey)

const currentGroup = computed(() => {
  const fallback = sampleGroups[0]
  return sampleGroups.find((group) => group.key === selectedKey.value) ?? fallback
})
</script>

<template>
  <section class="showcase">
    <header class="hero">
      <span class="badge">数据样例</span>
      <h1>典型内容样例库</h1>
      <p>从近期重标注的 USB 以及 WildGuard 数据集中挑选的代表性样本，用于前端快速对照比对。</p>
    </header>

    <section class="panel">
      <div class="panel-header">
        <div class="field select-field">
          <label for="showcase-select">样例类型</label>
          <select id="showcase-select" v-model="selectedKey">
            <option v-for="group in sampleGroups" :key="group.key" :value="group.key">
              {{ group.label }}
            </option>
          </select>
        </div>
        <div class="panel-meta">
          <h2>{{ currentGroup.label }}样例</h2>
          <p>{{ currentGroup.description }}</p>
        </div>
      </div>

      <div class="samples">
        <article v-for="sample in currentGroup.samples" :key="sample.id" class="sample-card">
          <header class="sample-card__header">
            <span class="dataset">{{ sample.dataset }}</span>
            <h3>{{ sample.title }}</h3>
          </header>

          <p v-if="sample.prompt" class="sample-card__prompt">「{{ sample.prompt }}」</p>
          <p v-if="sample.primaryText" class="sample-card__primary">{{ sample.primaryText }}</p>
          <p v-if="sample.secondaryText" class="sample-card__secondary">{{ sample.secondaryText }}</p>

          <figure v-if="sample.image" class="sample-card__media">
            <img :src="sample.image.src" :alt="sample.image.alt" loading="lazy" />
            <figcaption v-if="sample.narrative">{{ sample.narrative }}</figcaption>
          </figure>

          <p v-else-if="sample.narrative" class="sample-card__narrative">{{ sample.narrative }}</p>

          <p
            v-if="sample.modelDecision"
            :class="[
              'sample-card__decision',
              sample.decisionTone ? `tone-${sample.decisionTone}` : '',
            ]"
          >
            {{ sample.modelDecision }}
          </p>
          <p v-if="sample.modelRationale" class="sample-card__rationale">
            {{ sample.modelRationale }}
          </p>

          <ul v-if="sample.annotations?.length" class="sample-card__annotations">
            <li v-for="note in sample.annotations" :key="note">{{ note }}</li>
          </ul>
        </article>
      </div>
    </section>
  </section>
</template>

<style scoped>
.showcase {
  display: flex;
  flex-direction: column;
  gap: 2.5rem;
}

.hero {
  padding: 2.25rem;
  border-radius: 24px;
  background: linear-gradient(135deg, rgba(74, 58, 255, 0.14), rgba(66, 204, 255, 0.22));
  box-shadow: 0 20px 48px -24px rgba(30, 40, 90, 0.4);
  text-align: center;
  color: #0c0f2b;
}

.hero .badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.85rem;
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
  max-width: 44rem;
  margin: 0 auto;
  color: rgba(12, 15, 43, 0.8);
  font-size: 1.05rem;
}

.panel {
  padding: 2.25rem;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow:
    0 14px 40px -18px rgba(28, 35, 70, 0.3),
    0 4px 18px -12px rgba(28, 35, 70, 0.15);
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.panel-header {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  align-items: flex-start;
  justify-content: space-between;
}

.select-field {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 220px;
}

.select-field label {
  font-size: 0.95rem;
  font-weight: 600;
  color: #3a4270;
}

.select-field select {
  border-radius: 14px;
  border: 1px solid rgba(76, 110, 255, 0.25);
  padding: 0.8rem 1rem;
  font-size: 0.95rem;
  background: rgba(244, 247, 255, 0.7);
  color: #27315c;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.select-field select:focus {
  outline: none;
  border-color: rgba(76, 110, 255, 0.75);
  box-shadow: 0 0 0 3px rgba(76, 110, 255, 0.2);
}

.panel-meta h2 {
  font-size: 1.35rem;
  font-weight: 700;
  color: #122052;
  margin-bottom: 0.5rem;
}

.panel-meta p {
  max-width: 38rem;
  color: #4c5680;
  font-size: 0.98rem;
  line-height: 1.6;
}

.samples {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
}

.sample-card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  border-radius: 20px;
  padding: 1.5rem;
  background: rgba(244, 247, 255, 0.8);
  border: 1px solid rgba(112, 136, 255, 0.15);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.sample-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 36px -18px rgba(28, 35, 70, 0.35);
}

.sample-card__header {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.sample-card__header .dataset {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(49, 61, 122, 0.7);
}

.sample-card__header h3 {
  font-size: 1.15rem;
  font-weight: 700;
  color: #1a2553;
}

.sample-card__prompt,
.sample-card__primary,
.sample-card__secondary,
.sample-card__narrative {
  font-size: 0.95rem;
  color: #2f3866;
  line-height: 1.6;
}

.sample-card__prompt {
  font-weight: 600;
  color: #1e2f6b;
}

.sample-card__media {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  border-radius: 18px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 12px 32px -20px rgba(28, 35, 70, 0.4);
}

.sample-card__media img {
  width: 100%;
  display: block;
}

.sample-card__media figcaption {
  padding: 0.75rem 1rem;
  font-size: 0.9rem;
  color: #49527c;
  background: rgba(244, 247, 255, 0.9);
}

.sample-card__decision {
  border-radius: 14px;
  padding: 0.55rem 0.85rem;
  font-size: 0.9rem;
  font-weight: 600;
  background: rgba(76, 110, 255, 0.16);
  color: #1e2f6b;
}

.sample-card__decision.tone-safe {
  background: rgba(46, 204, 113, 0.16);
  color: #1b5e20;
}

.sample-card__decision.tone-unsafe {
  background: rgba(255, 97, 97, 0.16);
  color: #8b1a1a;
}

.sample-card__rationale {
  font-size: 0.9rem;
  color: #3c4570;
  line-height: 1.55;
}

.sample-card__annotations {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.sample-card__annotations li {
  border-radius: 999px;
  padding: 0.35rem 0.7rem;
  font-size: 0.8rem;
  background: rgba(76, 110, 255, 0.12);
  color: #26336b;
  font-weight: 600;
}

@media (max-width: 720px) {
  .panel {
    padding: 1.75rem;
  }

  .samples {
    grid-template-columns: 1fr;
  }
}
</style>
