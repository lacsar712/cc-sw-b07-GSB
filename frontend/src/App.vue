<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api.js'

const route = useRoute()
const router = useRouter()
const token = ref(localStorage.getItem('tok') || '')
const role = ref(localStorage.getItem('role') || '')
const user = ref(localStorage.getItem('user') || '')
const err = ref('')
const loginForm = ref({ username: 'calibrator', password: 'calib123456' })
const gate = ref(null)
let gateTimer

const isHome = computed(() => route.path === '/')
const isDetail = computed(() => route.path.startsWith('/jobs/'))
const isGate = computed(() => route.path === '/gate')
const holding = computed(() => !!gate.value?.holding)

async function refreshGate() {
  if (!localStorage.getItem('tok')) return
  try {
    gate.value = await api('/api/gate')
  } catch {
    // 角落提示静默失败，不打断页面
  }
}

async function login() {
  err.value = ''
  try {
    const data = await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({
        username: loginForm.value.username,
        password: loginForm.value.password,
      }),
    })
    token.value = data.access_token
    role.value = data.role
    user.value = data.username
    localStorage.setItem('tok', token.value)
    localStorage.setItem('role', role.value)
    localStorage.setItem('user', user.value)
    refreshGate()
    router.push('/')
  } catch (e) {
    err.value = String(e.message || e)
  }
}

function logout() {
  token.value = ''
  role.value = ''
  user.value = ''
  gate.value = null
  localStorage.clear()
  router.push('/')
}

onMounted(() => {
  refreshGate()
  gateTimer = setInterval(refreshGate, 2000)
})
onUnmounted(() => clearInterval(gateTimer))
</script>

<template>
  <div class="app-root">
    <header v-if="token" class="topbar">
      <div class="brand">光谱波长校准台</div>
      <nav class="nav">
        <router-link to="/" :class="{ active: isHome }">校准总览</router-link>
        <span class="nav-sep">|</span>
        <span
          class="nav-hint"
          :class="{ active: isDetail }"
          title="请从总表点击任务行进入"
        >任务详情</span>
        <span class="nav-sep">|</span>
        <router-link to="/gate" :class="{ active: isGate }">缓领闸</router-link>
      </nav>
      <div class="user-area">
        <span>{{ user }}（{{ role }}）</span>
        <button type="button" @click="logout">退出</button>
      </div>
    </header>

    <main class="main" :class="{ 'with-topbar': !!token }">
      <template v-if="!token">
        <h1>光谱波长校准台</h1>
        <section class="login-box">
          <h3>登录</h3>
          <label>用户名 <input v-model="loginForm.username" /></label>
          <label>密码 <input type="password" v-model="loginForm.password" /></label>
          <button type="button" @click="login">登录</button>
          <p class="hint">默认可写：calibrator / calib123456；只读：inspector / insp123456</p>
        </section>
        <p v-if="err" class="err">{{ err }}</p>
      </template>
      <router-view v-else />
    </main>

    <div v-if="token && holding" class="corner-hint" title="角落提示：缓领闸生效中">
      缓领中：普通待处理暂停领取（剩 {{ gate.remaining_seconds }} 秒），急测待处理照常。
      <router-link to="/gate">查看缓领闸</router-link>
    </div>
  </div>
</template>

<style>
.app-root {
  font-family: sans-serif;
  min-height: 100vh;
}
.topbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 20px;
  background: #1a2332;
  color: #f0f4f8;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
}
.brand {
  font-weight: 700;
  font-size: 16px;
  white-space: nowrap;
}
.nav {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}
.nav a,
.nav-hint {
  color: #a8b8c8;
  text-decoration: none;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 14px;
}
.nav a:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.08);
}
.nav a.active,
.nav-hint.active {
  color: #fff;
  background: rgba(255, 255, 255, 0.15);
  font-weight: 600;
}
.nav-sep {
  color: #5a6a7a;
}
.nav-hint {
  cursor: default;
  opacity: 0.85;
}
.user-area {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  white-space: nowrap;
}
.user-area button {
  cursor: pointer;
}
.main {
  max-width: 920px;
  margin: 24px auto;
  padding: 0 12px;
}
.main.with-topbar {
  margin-top: 72px;
}
.login-box {
  margin: 16px 0;
  padding: 12px;
  border: 1px solid #ccc;
}
.login-box label {
  display: inline-block;
  margin-right: 12px;
}
.hint {
  color: #666;
  font-size: 13px;
}
.err {
  color: #b00020;
}
.corner-hint {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 200;
  max-width: 320px;
  padding: 10px 14px;
  background: #fff4e5;
  border: 1px solid #e0a030;
  border-radius: 6px;
  color: #7a4d00;
  font-size: 13px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}
.corner-hint a {
  color: #7a4d00;
  font-weight: 600;
}
</style>
