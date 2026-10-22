<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const mode = ref<'login' | 'register'>('login')
const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ username: '', password: '', confirm: '' })

const submitText = computed(() => (mode.value === 'login' ? '登录' : '注册并登录'))

const rules = computed<FormRules>(() => ({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 32, message: '用户名长度为 2–32 个字符', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (/\s/.test(value)) callback(new Error('用户名不能包含空格'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    ...(mode.value === 'register'
      ? [{ min: 8, max: 128, message: '密码长度为 8–128 个字符', trigger: 'blur' as const }]
      : []),
  ],
  confirm:
    mode.value === 'register'
      ? [
          { required: true, message: '请再次输入密码', trigger: 'blur' as const },
          {
            validator: (_rule: unknown, value: string, callback) => {
              if (value !== form.password) callback(new Error('两次输入的密码不一致'))
              else callback()
            },
            trigger: 'blur' as const,
          },
        ]
      : [],
}))

watch(mode, () => {
  form.confirm = ''
  formRef.value?.clearValidate()
})

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(form.username.trim(), form.password)
      ElMessage.success('登录成功')
    } else {
      await auth.register(form.username.trim(), form.password)
      ElMessage.success('注册成功，已自动登录')
    }
    const redirect =
      typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
        ? route.query.redirect
        : '/'
    router.replace(redirect)
  } catch {
    /* 错误提示由 axios 拦截器统一弹出 */
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <div class="brand">
        <el-icon :size="30"><Collection /></el-icon>
        <span>背单词助手</span>
      </div>

      <el-tabs v-model="mode" stretch>
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="submit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            size="large"
            placeholder="2–32 个字符"
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            size="large"
            type="password"
            show-password
            :placeholder="mode === 'register' ? '至少 8 位' : '请输入密码'"
            :autocomplete="mode === 'register' ? 'new-password' : 'current-password'"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-form-item v-if="mode === 'register'" label="确认密码" prop="confirm">
          <el-input
            v-model="form.confirm"
            size="large"
            type="password"
            show-password
            placeholder="再次输入密码"
            autocomplete="new-password"
            @keyup.enter="submit"
          />
        </el-form-item>

        <el-button type="primary" size="large" class="submit" :loading="loading" @click="submit">
          {{ submitText }}
        </el-button>
      </el-form>

      <div class="switch-tip text-muted">
        {{ mode === 'login' ? '还没有账号？' : '已有账号？' }}
        <el-button link type="primary" @click="mode = mode === 'login' ? 'register' : 'login'">
          {{ mode === 'login' ? '注册一个' : '去登录' }}
        </el-button>
      </div>

      <div class="back-tip">
        <el-button link @click="router.push('/')">← 返回首页</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
}
.login-card {
  width: 420px;
  max-width: 100%;
  border-radius: 16px;
}
.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 22px;
  font-weight: 700;
  color: #409eff;
  margin: 6px 0 18px;
}
.submit {
  width: 100%;
  margin-top: 4px;
}
.switch-tip {
  margin-top: 16px;
  text-align: center;
  font-size: 13px;
}
.back-tip {
  margin-top: 10px;
  text-align: center;
}
</style>
