<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

async function onLogout() {
  await auth.logout()
  ElMessage.success('已退出登录')
  router.push('/')
}

async function onDeleteAccount() {
  if (!auth.user) return
  try {
    await ElMessageBox.confirm(
      `将永久删除账号「${auth.user.username}」及其全部词书、记忆状态和学习记录，且不可恢复。`,
      '注销账号',
      { type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消' },
    )
    const { value } = await ElMessageBox.prompt('请输入当前密码以确认注销', '确认注销', {
      inputType: 'password',
      confirmButtonText: '永久删除',
      cancelButtonText: '取消',
    })
    await auth.deleteAccount(value)
    ElMessage.success('账号已注销')
    router.push('/login')
  } catch (err) {
    // 'cancel' / 'close' 为用户取消；其余错误由 axios 拦截器提示
    if (err === 'cancel' || err === 'close') return
  }
}

function onUnauthorized() {
  auth.clear()
  if (route.name !== 'login') {
    router.push({ name: 'login', query: { redirect: route.fullPath } })
  }
}

onMounted(() => window.addEventListener('auth:unauthorized', onUnauthorized))
onBeforeUnmount(() => window.removeEventListener('auth:unauthorized', onUnauthorized))
</script>

<template>
  <el-config-provider :locale="zhCn">
    <el-container class="layout">
      <el-aside width="210px" class="aside">
        <div class="logo">
          <el-icon :size="26"><Collection /></el-icon>
          <span>背单词助手</span>
        </div>
        <el-menu router :default-active="route.path" class="menu" aria-label="主导航">
          <el-menu-item index="/">
            <el-icon><HomeFilled /></el-icon><span>首页</span>
          </el-menu-item>
          <el-menu-item index="/study">
            <el-icon><Reading /></el-icon><span>今日学习</span>
          </el-menu-item>
          <el-menu-item index="/books">
            <el-icon><Notebook /></el-icon><span>词书管理</span>
          </el-menu-item>
          <el-menu-item index="/stats">
            <el-icon><DataAnalysis /></el-icon><span>学习统计</span>
          </el-menu-item>
          <el-menu-item index="/settings">
            <el-icon><Setting /></el-icon><span>设置</span>
          </el-menu-item>
        </el-menu>

        <div class="account">
          <template v-if="auth.user">
            <div class="account-name">
              <el-icon><UserFilled /></el-icon>
              <span>{{ auth.user.username }}</span>
            </div>
            <div class="account-actions">
              <el-button link size="small" @click="onLogout">退出登录</el-button>
              <el-button link size="small" type="danger" @click="onDeleteAccount">
                注销账号
              </el-button>
            </div>
          </template>
          <el-button v-else type="primary" plain class="login-btn" @click="router.push('/login')">
            登录 / 注册
          </el-button>
        </div>
      </el-aside>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-config-provider>
</template>

<style scoped>
.layout {
  height: 100%;
}
.aside {
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
}
.logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: 64px;
  font-size: 18px;
  font-weight: 700;
  color: #409eff;
  border-bottom: 1px solid #ebeef5;
}
.menu {
  border-right: none;
  flex: 1;
}

.account {
  padding: 14px 16px;
  border-top: 1px solid #ebeef5;
}
.account-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
}
.account-name span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.account-actions {
  display: flex;
  justify-content: space-between;
}
.login-btn {
  width: 100%;
}

.main {
  background: #f5f7fa;
  overflow-y: auto;
}

@media (max-width: 900px) {
  .layout {
    flex-direction: column;
    min-height: 100dvh;
  }
  .aside {
    width: 100% !important;
    border-right: none;
    border-bottom: 1px solid #e4e7ed;
  }
  .logo {
    height: 52px;
    justify-content: flex-start;
    padding: 0 16px;
  }
  .menu {
    display: flex;
    flex-direction: row;
    flex: none;
    overflow-x: auto;
  }
  .menu :deep(.el-menu-item) {
    flex: 0 0 auto;
    height: 46px;
    line-height: 46px;
  }
  .account {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 8px 16px;
  }
  .account-name {
    margin-bottom: 0;
    flex: 1;
  }
  .account-actions {
    justify-content: flex-end;
  }
  .main {
    overflow-y: visible;
  }
}

@media (max-width: 640px) {
  .logo span {
    font-size: 16px;
  }
  .menu :deep(.el-menu-item) {
    padding: 0 10px;
  }
  .menu :deep(.el-menu-item span) {
    font-size: 13px;
  }
  .account {
    flex-wrap: wrap;
  }
  .account-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
