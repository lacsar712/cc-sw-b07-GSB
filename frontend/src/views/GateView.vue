<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api.js'

const role = ref(localStorage.getItem('role') || '')
const gate = ref(null)
const err = ref('')
const saved = ref('')
const form = ref({ threshold: 2, pause_seconds: 30 })
let timer
let savedTimer

const isWriter = computed(() => role.value === 'writer')

async function refresh() {
  if (!localStorage.getItem('tok')) return
  try {
    const g = await api('/api/gate')
    gate.value = g
    err.value = ''
  } catch (e) {
    err.value = String(e.message || e)
  }
}

async function save() {
  err.value = ''
  saved.value = ''
  try {
    const g = await api('/api/gate/config', {
      method: 'PUT',
      body: JSON.stringify({
        threshold: Number(form.value.threshold),
        pause_seconds: Number(form.value.pause_seconds),
      }),
    })
    gate.value = g
    saved.value = '已保存，仅约束此后的新结案串'
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = ''), 3000)
  } catch (e) {
    err.value = String(e.message || e)
  }
}

function fmtTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

onMounted(() => {
  role.value = localStorage.getItem('role') || ''
  refresh().then(() => {
    if (gate.value) {
      form.value.threshold = gate.value.threshold
      form.value.pause_seconds = gate.value.pause_seconds
    }
  })
  timer = setInterval(refresh, 1000)
})
onUnmounted(() => {
  clearInterval(timer)
  clearTimeout(savedTimer)
})
</script>

<template>
  <div>
    <h2>缓领闸</h2>
    <p v-if="err" style="color:#b00020">{{ err }}</p>
    <div v-if="gate" class="gate-grid">
      <section class="block">
        <h3>阈值设置</h3>
        <p class="big">{{ gate.threshold }} 条</p>
        <p class="desc">最近已结案连续超差达到该条数即自动缓领</p>
        <template v-if="isWriter">
          <label>连续超差阈值
            <input type="number" min="1" v-model.number="form.threshold" />
          </label>
        </template>
      </section>

      <section class="block">
        <h3>缓领秒数</h3>
        <p class="big">{{ gate.pause_seconds }} 秒</p>
        <p class="desc">缓领期间暂停领取普通待处理，急测待处理仍可领取</p>
        <template v-if="isWriter">
          <label>缓领秒数
            <input type="number" min="1" v-model.number="form.pause_seconds" />
          </label>
        </template>
      </section>

      <section class="block">
        <h3>当前是否缓领</h3>
        <p class="big" :class="gate.gating ? 'gating' : 'idle'">
          {{ gate.gating ? '正在缓领' : '未缓领' }}
        </p>
        <p class="desc" v-if="gate.gating">预计解除：{{ fmtTime(gate.release_at) }}</p>
        <p class="desc" v-else>当前连续超差 {{ gate.consecutive_overruns }} 条</p>
        <p v-if="!isWriter" class="desc">巡检员仅可查看，不能修改阈值与秒数</p>
      </section>

      <section class="block">
        <h3>起止流水</h3>
        <table v-if="gate.journal.length" class="journal">
          <thead>
            <tr><th>时间</th><th>动作</th><th>阈值</th><th>秒数</th><th>连续超差</th><th>触发任务</th></tr>
          </thead>
          <tbody>
            <tr v-for="j in gate.journal" :key="j.id">
              <td>{{ fmtTime(j.created_at) }}</td>
              <td>{{ j.action }}</td>
              <td>{{ j.threshold_snapshot }}</td>
              <td>{{ j.pause_seconds_snapshot }}</td>
              <td>{{ j.consecutive_overruns }}</td>
              <td>{{ j.trigger_job_id ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="desc">暂无缓领起止记录</p>
      </section>
    </div>

    <div v-if="isWriter" class="save-bar">
      <button type="button" @click="save">保存阈值与秒数</button>
      <span v-if="saved" class="saved">{{ saved }}</span>
    </div>
  </div>
</template>

<style scoped>
.gate-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin: 16px 0;
}
.block {
  padding: 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.block h3 {
  margin-top: 0;
}
.big {
  font-size: 22px;
  font-weight: 700;
  margin: 6px 0;
}
.big.gating {
  color: #b00020;
}
.big.idle {
  color: #1a7f37;
}
.desc {
  color: #666;
  font-size: 13px;
}
.journal {
  border-collapse: collapse;
  width: 100%;
  font-size: 13px;
}
.journal th,
.journal td {
  border: 1px solid #ddd;
  padding: 4px 6px;
  text-align: left;
}
.save-bar {
  display: flex;
  align-items: center;
  gap: 10px;
}
.saved {
  color: #1a7f37;
  font-size: 13px;
}
</style>
