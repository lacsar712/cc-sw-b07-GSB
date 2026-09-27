<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api.js'

const role = ref(localStorage.getItem('role') || '')
const gate = ref(null)
const err = ref('')
const msg = ref('')
const thresholdInput = ref(2)
const secondsInput = ref(30)
let timer

const isWriter = computed(() => role.value === 'writer')

async function refresh() {
  if (!localStorage.getItem('tok')) return
  try {
    const g = await api('/api/gate')
    gate.value = g
    thresholdInput.value = g.threshold
    secondsInput.value = g.hold_seconds
    err.value = ''
  } catch (e) {
    err.value = String(e.message || e)
  }
}

async function save() {
  err.value = ''
  msg.value = ''
  try {
    await api('/api/gate/settings', {
      method: 'PUT',
      body: JSON.stringify({
        threshold: Number(thresholdInput.value),
        hold_seconds: Number(secondsInput.value),
      }),
    })
    msg.value = '已保存，只约束此后新结案串，旧流水不追溯改写'
    await refresh()
  } catch (e) {
    err.value = String(e.message || e)
  }
}

function fmtTime(t) {
  if (!t) return '—'
  return new Date(t).toLocaleString()
}

function eventName(e) {
  if (e === 'hold_start') return '开始缓领'
  if (e === 'hold_end') return '解除缓领'
  return e
}

onMounted(() => {
  role.value = localStorage.getItem('role') || ''
  refresh()
  timer = setInterval(refresh, 1000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div>
    <h2>缓领闸</h2>
    <p v-if="err" style="color:#b00020">{{ err }}</p>
    <p v-if="msg" style="color:#1a7f37">{{ msg }}</p>

    <section class="block">
      <h3>阈值设置</h3>
      <p>连续超差达到该条数即自动开始缓领。</p>
      <template v-if="isWriter">
        <label>连续超差阈值（条）
          <input type="number" min="1" max="50" step="1" v-model.number="thresholdInput" />
        </label>
        <button type="button" @click="save">保存</button>
      </template>
      <template v-else>
        <p>当前阈值：<b>{{ gate?.threshold ?? '—' }}</b> 条（巡检员只读，不能修改）</p>
      </template>
    </section>

    <section class="block">
      <h3>缓领秒数</h3>
      <p>开始缓领后，普通待处理暂停领取的时长；急测待处理不受影响。</p>
      <template v-if="isWriter">
        <label>缓领秒数（秒）
          <input type="number" min="1" max="3600" step="1" v-model.number="secondsInput" />
        </label>
        <button type="button" @click="save">保存</button>
      </template>
      <template v-else>
        <p>当前缓领秒数：<b>{{ gate?.hold_seconds ?? '—' }}</b> 秒（巡检员只读，不能修改）</p>
      </template>
    </section>

    <section class="block">
      <h3>当前是否缓领</h3>
      <p v-if="gate?.holding" class="holding">
        正在缓领：剩余 {{ gate.remaining_seconds }} 秒（至 {{ fmtTime(gate.hold_until) }}），
        普通待处理暂停领取，急测待处理照常。
      </p>
      <p v-else class="idle">未在缓领，普通待处理正常领取。</p>
      <p>当前最近已结案连续超差：<b>{{ gate?.streak ?? 0 }}</b> 条
        （阈值 {{ gate?.threshold ?? '—' }} 条）。</p>
      <p v-if="gate?.updated_by" class="meta">
        阈值与秒数最近由 {{ gate.updated_by }} 于 {{ fmtTime(gate.updated_at) }} 设定。
      </p>
    </section>

    <section class="block">
      <h3>起止流水</h3>
      <table v-if="gate?.events?.length" border="1" cellpadding="6" style="border-collapse:collapse; width:100%;">
        <thead>
          <tr><th>编号</th><th>时间</th><th>事件</th><th>详情</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in gate.events" :key="e.id">
            <td>{{ e.id }}</td>
            <td>{{ fmtTime(e.created_at) }}</td>
            <td>{{ eventName(e.event) }}</td>
            <td>{{ e.detail }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else>暂无缓领起止记录。</p>
    </section>
  </div>
</template>

<style scoped>
.block {
  margin: 16px 0;
  padding: 12px;
  border: 1px solid #ccc;
}
.block label {
  display: inline-block;
  margin-right: 12px;
}
.holding {
  color: #b00020;
  font-weight: 600;
}
.idle {
  color: #1a7f37;
}
.meta {
  color: #666;
  font-size: 13px;
}
</style>
