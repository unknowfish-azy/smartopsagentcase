<template>
  <StellarOceanProvider state="thinking">
  <main ref="loginShellRef" class="login-shell" :data-visual-mode="visualMode" :data-theme="resolvedTheme" @pointermove="moveBubbleLight" @pointerleave="resetBubbleLight">
    <!-- 静态背景图：深空星海（public/assets/login-cover.jpg，静态资源，各视觉档位通用；动效层叠加其上） -->
    <div class="login-cover-image" aria-hidden="true"></div>
    <!-- §8 Gate-1 CanvasAmbientField: 桌面端才挂载 + 移动端轻量降级（70 颗 + 无连线） -->
    <CanvasAmbientField v-if="!isMobile" class="login-ambient" :palette-root="loginShellRef" :star-multiplier="visualMode === 'lightweight' ? 1 : 1.8" :connect-particles="visualMode !== 'lightweight'" :connect-max-dist="130" />
    <!-- §8 Gate-2 封面视频槽：balanced 档 + 桌面端 + 仅当 public/assets/login-cover.mp4 存在时才挂载 -->
    <video v-if="!isMobile && visualMode === 'balanced'" class="login-cover-video" :poster="loginCoverPoster" autoplay muted loop playsinline preload="metadata"></video>
    <!-- §8 Gate-3 暗遮罩：视频层叠用（40% 暗，按最亮帧验对比度） -->
    <div v-if="!isMobile" class="login-cover-mask" aria-hidden="true"></div>
    <!-- 极光光带：中景层大尺度缓慢漂移（零 KB，CSS 渐变 + transform） -->
    <div v-if="!isMobile && visualMode !== 'reduced-motion'" class="login-aurora" aria-hidden="true"></div>
    <!-- 上浮气泡层：零 KB 纯 CSS（radial-gradient 泡壁 + translate3d 上浮），lightweight 档减量、reduced-motion 不挂载 -->
    <div v-if="!isMobile && visualMode !== 'reduced-motion'" class="login-bubbles" aria-hidden="true">
      <span v-for="b in bubbles" :key="b.id" :style="b.style"></span>
    </div>
    <MeteorShower v-if="!isMobile && visualMode === 'balanced'" class="login-meteors" />
    <!-- 边缘荧光链路：左右神经走线 + 底部服务拓扑。零依赖 SVG（CSS 流光 + SMIL 脉冲），
         呼应"维系上下文"主题；桌面端挂载，reduced-motion 档不渲染，lightweight 档转静态。 -->
    <!-- 渐变定义：走线两端淡出、光点径向柔光。颜色走令牌，明暗主题自动切换。 -->
    <svg v-if="!isMobile && visualMode !== 'reduced-motion'" class="login-traces-defs" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="login-trace-fade-cyan" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" style="stop-color: var(--smart-primary-strong)" stop-opacity="0" />
          <stop offset=".35" style="stop-color: var(--smart-primary-strong)" stop-opacity=".55" />
          <stop offset=".65" style="stop-color: var(--smart-primary-strong)" stop-opacity=".55" />
          <stop offset="1" style="stop-color: var(--smart-primary-strong)" stop-opacity="0" />
        </linearGradient>
        <linearGradient id="login-trace-fade-green" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" style="stop-color: var(--smart-effect-primary)" stop-opacity="0" />
          <stop offset=".35" style="stop-color: var(--smart-effect-primary)" stop-opacity=".48" />
          <stop offset=".65" style="stop-color: var(--smart-effect-primary)" stop-opacity=".48" />
          <stop offset="1" style="stop-color: var(--smart-effect-primary)" stop-opacity="0" />
        </linearGradient>
        <linearGradient id="login-trace-wire-fade" gradientUnits="userSpaceOnUse" x1="140" y1="46" x2="580" y2="46">
          <stop offset="0" style="stop-color: var(--smart-primary-strong)" stop-opacity="0" />
          <stop offset=".25" style="stop-color: var(--smart-primary-strong)" stop-opacity=".32" />
          <stop offset=".75" style="stop-color: var(--smart-primary-strong)" stop-opacity=".32" />
          <stop offset="1" style="stop-color: var(--smart-primary-strong)" stop-opacity="0" />
        </linearGradient>
        <radialGradient id="login-trace-core-cyan">
          <stop offset="0" style="stop-color: var(--smart-effect-star)" stop-opacity=".8" />
          <stop offset=".3" style="stop-color: var(--smart-primary-strong)" stop-opacity=".55" />
          <stop offset="1" style="stop-color: var(--smart-primary-strong)" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="login-trace-core-green">
          <stop offset="0" style="stop-color: var(--smart-effect-star)" stop-opacity=".8" />
          <stop offset=".3" style="stop-color: var(--smart-effect-primary)" stop-opacity=".5" />
          <stop offset="1" style="stop-color: var(--smart-effect-primary)" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="login-trace-pulse-cyan">
          <stop offset="0" style="stop-color: var(--smart-effect-star)" stop-opacity=".8" />
          <stop offset=".4" style="stop-color: var(--smart-primary-strong)" stop-opacity=".4" />
          <stop offset="1" style="stop-color: var(--smart-primary-strong)" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="login-trace-pulse-green">
          <stop offset="0" style="stop-color: var(--smart-effect-star)" stop-opacity=".8" />
          <stop offset=".4" style="stop-color: var(--smart-effect-primary)" stop-opacity=".36" />
          <stop offset="1" style="stop-color: var(--smart-effect-primary)" stop-opacity="0" />
        </radialGradient>
      </defs>
    </svg>
    <svg v-if="!isMobile && visualMode !== 'reduced-motion'" class="login-traces login-traces--left" viewBox="0 0 90 720" preserveAspectRatio="xMinYMin slice" aria-hidden="true">
      <path class="login-traces__aura" d="M 24 40 V 150 L 44 170 V 330 L 24 350 V 600" />
      <path class="login-traces__aura login-traces__aura--green" d="M 48 70 V 200 L 32 218 V 470 L 48 488 V 640" />
      <path class="login-traces__base" d="M 24 40 V 150 L 44 170 V 330 L 24 350 V 600" />
      <path class="login-traces__glow" style="--flow-dur: 5.2s" d="M 24 40 V 150 L 44 170 V 330 L 24 350 V 600" />
      <path class="login-traces__base login-traces__base--green" d="M 48 70 V 200 L 32 218 V 470 L 48 488 V 640" />
      <path class="login-traces__glow login-traces__glow--green" style="--flow-dur: 6.8s" d="M 48 70 V 200 L 32 218 V 470 L 48 488 V 640" />
      <circle class="login-traces__node" cx="24" cy="150" r="4" />
      <circle class="login-traces__node" cx="44" cy="330" r="4" />
      <circle class="login-traces__node login-traces__node--green" cx="48" cy="200" r="3.4" />
      <circle class="login-traces__node login-traces__node--green" cx="32" cy="470" r="3.4" />
      <circle class="login-traces__ring" cx="24" cy="600" r="4" />
      <circle class="login-traces__pulse" r="5.5"><animateMotion dur="5.2s" repeatCount="indefinite" path="M 24 40 V 150 L 44 170 V 330 L 24 350 V 600" /></circle>
      <circle class="login-traces__pulse login-traces__pulse--green" r="4.8"><animateMotion dur="6.8s" begin="1.4s" repeatCount="indefinite" path="M 48 70 V 200 L 32 218 V 470 L 48 488 V 640" /></circle>
    </svg>
    <svg v-if="!isMobile && visualMode !== 'reduced-motion'" class="login-traces login-traces--right" viewBox="0 0 90 720" preserveAspectRatio="xMaxYMin slice" aria-hidden="true">
      <path class="login-traces__aura" d="M 66 40 V 150 L 46 170 V 330 L 66 350 V 600" />
      <path class="login-traces__aura login-traces__aura--green" d="M 42 70 V 200 L 58 218 V 470 L 42 488 V 640" />
      <path class="login-traces__base" d="M 66 40 V 150 L 46 170 V 330 L 66 350 V 600" />
      <path class="login-traces__glow" style="--flow-dur: 5.6s" d="M 66 40 V 150 L 46 170 V 330 L 66 350 V 600" />
      <path class="login-traces__base login-traces__base--green" d="M 42 70 V 200 L 58 218 V 470 L 42 488 V 640" />
      <path class="login-traces__glow login-traces__glow--green" style="--flow-dur: 6.2s" d="M 42 70 V 200 L 58 218 V 470 L 42 488 V 640" />
      <circle class="login-traces__node" cx="66" cy="150" r="4" />
      <circle class="login-traces__node" cx="46" cy="330" r="4" />
      <circle class="login-traces__node login-traces__node--green" cx="42" cy="200" r="3.4" />
      <circle class="login-traces__node login-traces__node--green" cx="58" cy="470" r="3.4" />
      <circle class="login-traces__ring" cx="66" cy="600" r="4" />
      <circle class="login-traces__pulse" r="5.5"><animateMotion dur="5.6s" begin="2s" repeatCount="indefinite" path="M 66 40 V 150 L 46 170 V 330 L 66 350 V 600" /></circle>
      <circle class="login-traces__pulse login-traces__pulse--green" r="4.8"><animateMotion dur="6.2s" begin=".6s" repeatCount="indefinite" path="M 42 70 V 200 L 58 218 V 470 L 42 488 V 640" /></circle>
    </svg>
    <svg v-if="!isMobile && visualMode !== 'reduced-motion'" class="login-traces login-traces--bottom" viewBox="0 0 720 72" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <line class="login-traces__wire" x1="140" y1="46" x2="580" y2="46" />
      <rect class="login-traces__chip" x="116" y="38" width="48" height="16" rx="8" />
      <text class="login-traces__chip-label" x="140" y="49" text-anchor="middle">GATEWAY</text>
      <rect class="login-traces__chip" x="228" y="38" width="44" height="16" rx="8" />
      <text class="login-traces__chip-label" x="250" y="49" text-anchor="middle">AGENT</text>
      <rect class="login-traces__chip" x="338" y="38" width="74" height="16" rx="8" />
      <text class="login-traces__chip-label" x="375" y="49" text-anchor="middle">KNOWLEDGE</text>
      <rect class="login-traces__chip" x="490" y="38" width="50" height="16" rx="8" />
      <text class="login-traces__chip-label" x="515" y="49" text-anchor="middle">SESSION</text>
      <circle class="login-traces__pulse" r="5"><animateMotion dur="6s" repeatCount="indefinite" path="M 162 46 H 515" /></circle>
      <circle class="login-traces__pulse login-traces__pulse--green" r="4.4"><animateMotion dur="6s" begin="3s" repeatCount="indefinite" path="M 515 46 H 162" /></circle>
    </svg>
    <!-- 角落缀饰：左下「记忆星座图」/ 右下「运维雷达阵」。延续走线语言（令牌配色 + SMIL 脉冲），
         填充两下角空旷区；reduced-motion 档不挂载，lightweight 档去动效，移动端隐藏。 -->
    <svg v-if="!isMobile && visualMode !== 'reduced-motion'" class="login-corner-deco login-corner-deco--bl" viewBox="0 0 380 252" preserveAspectRatio="xMinYMax meet" aria-hidden="true">
      <path class="login-corner-deco__arc" d="M 116 252 A 116 116 0 0 0 0 136" />
      <path class="login-corner-deco__arc" d="M 178 252 A 178 178 0 0 0 0 74" />
      <path class="login-corner-deco__arc login-corner-deco__arc--dashed" d="M 236 252 A 236 236 0 0 0 0 16" />
      <polyline class="login-corner-deco__constellation" points="58,196 108,148 156,172 198,112 246,138 292,96" />
      <circle class="login-corner-deco__star" cx="58" cy="196" r="3.2" />
      <circle class="login-corner-deco__star login-corner-deco__star--green" cx="108" cy="148" r="2.8" />
      <circle class="login-corner-deco__star" cx="156" cy="172" r="2.4" />
      <circle class="login-corner-deco__star" cx="198" cy="112" r="3.6" />
      <circle class="login-corner-deco__star login-corner-deco__star--green" cx="246" cy="138" r="2.8" />
      <circle class="login-corner-deco__star" cx="292" cy="96" r="2.4" />
      <path class="login-corner-deco__tick" d="M 132 214 h 8 M 136 210 v 8" />
      <path class="login-corner-deco__tick" d="M 226 178 h 8 M 230 174 v 8" />
      <path class="login-corner-deco__tick" d="M 316 62 h 8 M 320 58 v 8" />
      <circle class="login-corner-deco__orbit" r="4.6"><animateMotion dur="14s" repeatCount="indefinite" path="M 116 252 A 116 116 0 0 0 0 136" /></circle>
      <text class="login-corner-deco__label" x="150" y="238" text-anchor="middle">MEM · SECTOR A3</text>
    </svg>
    <svg v-if="!isMobile && visualMode !== 'reduced-motion'" class="login-corner-deco login-corner-deco--br" viewBox="0 0 340 264" preserveAspectRatio="xMaxYMax meet" aria-hidden="true">
      <path class="login-corner-deco__sweep" d="M 340 264 L 340 58 A 206 206 0 0 0 138 260 Z" />
      <path class="login-corner-deco__arc" d="M 248 264 A 92 92 0 0 1 340 172" />
      <path class="login-corner-deco__arc" d="M 186 264 A 154 154 0 0 1 340 110" />
      <path class="login-corner-deco__arc login-corner-deco__arc--dashed" d="M 122 264 A 218 218 0 0 1 340 46" />
      <path class="login-corner-deco__spoke" d="M 340 264 L 231 155" />
      <path class="login-corner-deco__spoke" d="M 340 264 L 278 132" />
      <path class="login-corner-deco__tick" d="M 288 250 h 10 M 293 245 v 10" />
      <circle class="login-corner-deco__star" cx="322" cy="238" r="2.6" />
      <circle class="login-corner-deco__orbit" r="4.4"><animateMotion dur="16s" repeatCount="indefinite" path="M 186 264 A 154 154 0 0 1 340 110" /></circle>
      <circle class="login-corner-deco__orbit login-corner-deco__orbit--green" r="3.8"><animateMotion dur="16s" begin="8s" repeatCount="indefinite" path="M 340 172 A 92 92 0 0 1 248 264" /></circle>
      <text class="login-corner-deco__label" x="212" y="250" text-anchor="middle">OPS GRID · SECTOR B7</text>
    </svg>
    <header class="login-topbar">
      <div class="login-brand"><span class="login-brand__mark login-brand__mark--star" aria-hidden="true"><BrandMark :size="26" /></span><div><strong>智维 Agent</strong><span>SMARTOPS · SPARKING OPERATIONS</span></div></div>
      <div class="login-appearance" aria-label="外观设置">
        <label><span>主题</span><select aria-label="选择主题模式" :value="themeMode" @change="setThemeMode($event.target.value)"><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label>
        <label><span>视觉</span><select aria-label="选择视觉模式" :value="visualMode" @change="setVisualMode($event.target.value)"><option value="balanced">平衡视觉</option><option value="lightweight">轻量视觉</option><option value="reduced-motion">减少动态</option></select></label>
      </div>
    </header>
    <div class="login-layout">
    <section class="login-showcase" aria-label="智维工作空间介绍">
      <div class="login-copy">
      <div class="login-copy__emblem" aria-hidden="true"><BrandMark :size="64" /></div>
      <p class="editorial-label">个人运维知识空间</p>
      <h1>智驭系统<br><span>维系上下文</span></h1>
      <p class="login-copy__description">把知识、系统与运维记忆连接起来，<br class="desktop-break">让每一次操作都有清晰的上下文。</p>
      </div>
      <dl class="login-trust">
        <div><dt>身份认证</dt><dd>服务端验证</dd></div>
        <div><dt>访问权限</dt><dd>按账号授权</dd></div>
        <div><dt>会话保护</dt><dd>安全令牌校验</dd></div>
      </dl>
      <div class="login-organisms login-organisms--spark" aria-hidden="true">
        <div class="login-stars-bg"></div>
        <div class="login-stars-front"></div>
        <span class="login-scene-label">KNOWLEDGE · MEMORY · AGENT</span>
      </div>
    </section>
    <form ref="glassCard" class="login-form login-form--portal" aria-labelledby="login-title" @pointermove="moveGlassLight" @pointerleave="resetGlassLight" @submit.prevent="submit" novalidate>
      <header class="login-form__header">
        <div>
          <p class="editorial-label">你的工作空间 / SECURE ENTRY</p>
          <h2 id="login-title">{{ pendingMfa ? '二次认证' : registering ? '注册普通账号' : '欢迎回来' }}</h2>
          <p>{{ registering ? '注册账号固定为运维用户，管理员不开放注册。' : form.portal === 'admin' ? '仅限已授权管理员进入管理工作台。' : '继续你的知识与运维工作。' }}</p>
        </div>
        <span class="login-form__status"><span aria-hidden="true"></span>LOCAL</span>
      </header>

      <MfaChallenge v-if="pendingMfa" :challenge="pendingMfa" @verified="finishLogin" @cancel="pendingMfa = null; error = ''" />
      <template v-else>
      <div v-if="!registering" class="role-switcher" role="tablist" aria-label="登录入口">
        <button v-for="entry in portals" :id="`portal-${entry.id}`" :key="entry.id" type="button" role="tab" aria-controls="portal-fields" :aria-selected="form.portal === entry.id" :tabindex="form.portal === entry.id ? 0 : -1" :class="{ 'is-active': form.portal === entry.id }" :disabled="loading" @click="switchPortal(entry.id)" @keydown.left.prevent="selectPortal" @keydown.right.prevent="selectPortal"><span class="role-switcher__dot" aria-hidden="true"></span>{{ entry.label }}</button>
      </div>
      <!-- 两个入口各由独立服务提供，切换会改变地址；提前说明，避免被当成"页面乱跳"。 -->
      <p v-if="!registering && otherPortal" class="role-switcher__hint">
        切换{{ otherPortal.label }}：<code>{{ otherPortal.address }}</code>（独立服务，需重新登录）
      </p>
      <p v-if="route.query.reason === 'password-changed'" role="status">密码已更新，旧会话已退出，请重新登录。</p>
      <p v-if="route.query.reason === 'denied'" role="status">当前账号没有管理员入口。请使用管理员账号登录，或切换到用户门户。</p>
      <p v-if="success" class="login-form__notice" role="status">{{ success }}</p>
      <div id="portal-fields" class="login-form__fields" :role="registering ? 'group' : 'tabpanel'" :aria-label="registering ? '普通账号注册信息' : undefined" :aria-labelledby="registering ? undefined : `portal-${form.portal}`">
        <label class="login-field" :class="{ 'login-field--focused': focusedInput === 'username' }">
          <span class="login-field__label">账号</span>
          <span class="login-input-shell">
            <el-icon class="login-input-icon" aria-hidden="true"><User /></el-icon>
            <input v-model.trim="form.username" autocomplete="username" :disabled="loading" :aria-describedby="registering ? 'registration-guidance' : undefined" placeholder="输入运维账号" required @focus="focusedInput = 'username'" @blur="focusedInput = ''" @input="error = ''">
          </span>
        </label>

        <label class="login-field" :class="{ 'login-field--focused': focusedInput === 'password' }">
          <span class="login-field__label">密码</span>
          <span class="login-input-shell">
            <el-icon class="login-input-icon" aria-hidden="true"><Lock /></el-icon>
            <input v-model="form.password" :disabled="loading" :aria-describedby="registering ? 'registration-guidance' : undefined" :type="showPassword ? 'text' : 'password'" :autocomplete="registering ? 'new-password' : 'current-password'" :placeholder="registering ? '设置登录密码' : '输入访问密码'" required @focus="focusedInput = 'password'" @blur="focusedInput = ''" @input="error = ''">
            <button class="password-visibility-toggle" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" :aria-pressed="showPassword" @click="showPassword = !showPassword">
              <el-icon aria-hidden="true"><View v-if="!showPassword" /><Hide v-else /></el-icon>
            </button>
          </span>
        </label>
      </div>

      <label v-if="registering" class="login-field">
        <span class="login-field__label">确认密码</span>
        <span class="login-input-shell"><el-icon class="login-input-icon" aria-hidden="true"><Lock /></el-icon><input v-model="form.confirmPassword" :disabled="loading" aria-describedby="registration-guidance" type="password" autocomplete="new-password" placeholder="再次输入密码" required></span>
      </label>
      <p v-if="registering" id="registration-guidance" class="login-form__guidance">账号为 3–64 位字母、数字、点、下划线或短横线。普通密码至少 {{ policy?.userPasswordMinLength || 12 }} 字符，管理员新密码至少 {{ policy?.adminPasswordMinLength || 16 }} 字符，均不超过 {{ policy?.passwordMaxBytes || 72 }} UTF-8 字节。</p>

      <div v-if="!registering" class="login-form__options">
        <label class="remember-control"><input v-model="rememberMe" type="checkbox"><span>记住本机账号</span></label>
        <span class="login-form__policy">最小权限 · 全程留痕</span>
      </div>

      <HumanVerification ref="humanCheck" :action="registering ? 'register' : form.portal === 'admin' ? 'admin_login' : 'login'" :disabled="loading" @change="updateHumanState" />
      <p v-if="error" id="login-error" class="login-form__error" role="alert">{{ error }}</p>
      <button class="login-submit" type="submit" :disabled="loading || !humanState.ready || (registering && !policy?.enabled)">
        <span>{{ registering ? (loading ? '正在创建账号' : '创建普通账号') : (loading ? '正在建立安全会话' : '进入智维Agent') }}</span>
        <el-icon v-if="!loading" aria-hidden="true"><ArrowRight /></el-icon>
        <span v-else class="login-submit__spinner" aria-hidden="true"></span>
      </button>
      <div v-if="form.portal === 'user'" class="login-registration">
        <button v-if="registering" type="button" :disabled="loading" @click="setRegistration(false)">返回登录</button>
        <template v-else>
          <span v-if="policy?.enabled">首次使用？</span>
          <button type="button" :disabled="loading || !policy?.enabled" @click="setRegistration(true)">注册普通账号</button>
          <p v-if="policy && !policy.enabled" role="status">普通账号注册已关闭，请联系管理员。</p>
          <p v-else-if="policyError" role="alert">{{ policyError }} <button type="button" @click="loadPolicy">重试</button></p>
          <p v-else-if="!policy" role="status">正在读取注册状态…</p>
        </template>
      </div>
      <p v-else class="login-form__guidance">管理员不开放注册；新密码至少 16 字符且不超过 72 UTF-8 字节。已有账号仍可使用原密码登录。</p>
      <p class="login-form__footer">使用已创建的真实账号登录 · 会话空闲 {{ form.portal === 'admin' ? 10 : 30 }} 分钟后失效</p>
      </template>
    </form>
    </div>
    <footer class="login-page-footer"><span>SMARTOPS AGENT</span><span>知识 · 记忆 · 受控智能体</span></footer>
  </main>
  </StellarOceanProvider>
</template>

<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Hide, Lock, User, View } from '@element-plus/icons-vue'
import HumanVerification from '../../components/auth/HumanVerification.vue'
import MfaChallenge from '../../components/auth/MfaChallenge.vue'
import BrandMark from '../../components/common/BrandMark.vue'
import StellarOceanProvider from '../../components/common/StellarOceanProvider.vue'
import MeteorShower from '../../components/common/MeteorShower.vue'
import { loginSession, registrationPolicy, registerAccount } from '../../security/session.js'
import { sessionLanding } from '../../security/portalPolicy.js'
import { resolvePortalSwitch } from '../../security/portalSwitch.js'
import { registrationError } from '../../security/passwordPolicy.js'
import { themeMode, resolvedTheme, setThemeMode } from '../../theme.js'
import { visualMode, setVisualMode } from '../../visual/visualMode.js'

const CanvasAmbientField = defineAsyncComponent(() => import('../../components/common/CanvasAmbientField.vue'))

// §8 Gate-2: 移动端 <1024 不加载任何背景动效（T11 性能基线）
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 1024)

// §8 Gate-4: poster 占位图复用 starfield-placeholder.svg
const loginCoverPoster = '/assets/starfield-placeholder.svg'

/* 上浮气泡：确定性布局（不用 Math.random，保证每次渲染与截图/回归一致）。
   14 颗；lightweight 档由 CSS 只保留前 4 颗并放慢周期。
   --depth 为鼠标视差深度：大泡近（系数大），小泡远；--bubble-px/py 由 moveBubbleLight 写入。 */
const bubbles = [
  { id: 1, style: { left: '4%', width: '18px', height: '18px', '--dur': '14s', '--delay': '0s', '--sway': '26px', '--op': '.50', '--sc': '.9', '--depth': '.7' } },
  { id: 2, style: { left: '13%', width: '34px', height: '34px', '--dur': '20s', '--delay': '-9s', '--sway': '-34px', '--op': '.40', '--sc': '1', '--depth': '1.1' } },
  { id: 3, style: { left: '23%', width: '12px', height: '12px', '--dur': '12s', '--delay': '-4s', '--sway': '18px', '--op': '.56', '--sc': '.8', '--depth': '.5' } },
  { id: 4, style: { left: '32%', width: '44px', height: '44px', '--dur': '25s', '--delay': '-16s', '--sway': '-28px', '--op': '.34', '--sc': '1', '--depth': '1.3' } },
  { id: 5, style: { left: '42%', width: '22px', height: '22px', '--dur': '16s', '--delay': '-7s', '--sway': '30px', '--op': '.46', '--sc': '.95', '--depth': '.8' } },
  { id: 6, style: { left: '51%', width: '14px', height: '14px', '--dur': '13s', '--delay': '-11s', '--sway': '-20px', '--op': '.54', '--sc': '.85', '--depth': '.5' } },
  { id: 7, style: { left: '60%', width: '30px', height: '30px', '--dur': '22s', '--delay': '-3s', '--sway': '24px', '--op': '.38', '--sc': '1', '--depth': '1' } },
  { id: 8, style: { left: '69%', width: '16px', height: '16px', '--dur': '14s', '--delay': '-13s', '--sway': '-26px', '--op': '.52', '--sc': '.9', '--depth': '.6' } },
  { id: 9, style: { left: '78%', width: '26px', height: '26px', '--dur': '18s', '--delay': '-6s', '--sway': '20px', '--op': '.42', '--sc': '1', '--depth': '.9' } },
  { id: 10, style: { left: '86%', width: '10px', height: '10px', '--dur': '11s', '--delay': '-10s', '--sway': '-14px', '--op': '.58', '--sc': '.8', '--depth': '.4' } },
  { id: 11, style: { left: '9%', width: '24px', height: '24px', '--dur': '17s', '--delay': '-14s', '--sway': '-22px', '--op': '.44', '--sc': '.95', '--depth': '.75' } },
  { id: 12, style: { left: '37%', width: '13px', height: '13px', '--dur': '12s', '--delay': '-2s', '--sway': '16px', '--op': '.55', '--sc': '.85', '--depth': '.55' } },
  { id: 13, style: { left: '56%', width: '36px', height: '36px', '--dur': '24s', '--delay': '-19s', '--sway': '-30px', '--op': '.36', '--sc': '1', '--depth': '1.2' } },
  { id: 14, style: { left: '93%', width: '20px', height: '20px', '--dur': '15s', '--delay': '-8s', '--sway': '22px', '--op': '.48', '--sc': '.9', '--depth': '.95' } }
]

const router = useRouter()
const route = useRoute()
const form = reactive({ username: '', password: '', confirmPassword: '', portal: route.query.portal === 'admin' ? 'admin' : 'user' })
const portals = [{ id: 'user', label: '用户层' }, { id: 'admin', label: '管理员层' }]
const registering = ref(false)
const pendingMfa = ref(null)
const policy = ref(null)
const policyError = ref('')
const success = ref('')
const loading = ref(false)
const error = ref('')
const showPassword = ref(false)
const rememberMe = ref(false)
const focusedInput = ref('')
const glassCard = ref(null)
const loginShellRef = ref(null)
const humanCheck = ref(null)
const humanState = reactive({ token: '', ready: false })
function updateHumanState(state) { Object.assign(humanState, state) }

/**
 * 当前入口之外的另一个入口，以及它真实的地址。
 *
 * 端口是可配置的（VITE_SMARTOPS_ADMIN_PORT / VITE_SMARTOPS_USER_PORT），
 * 因此这里显示的是 resolvePortalSwitch 实际算出来的地址，而不是写死的字符串。
 */
const otherPortal = computed(() => {
  const target = form.portal === 'admin' ? 'user' : 'admin'
  const decision = resolvePortalSwitch(target, { query: { ...route.query } })
  if (!decision) return null
  return { id: target, label: target === 'admin' ? '管理员层' : '用户层', address: decision.url.replace(/^https?:\/\//, '').split('?')[0] }
})
let glassFrame = 0
let glassMotionQuery
let glassPointerX = 64
let glassPointerY = 8
let lastGlassWriteAt = 0
const GLASS_LIGHT_THROTTLE_MS = 30

function syncPortalUrl(portal) {
  if (!['user', 'admin'].includes(portal) || route.query.portal === portal) return
  router.replace({ path: '/login', query: { ...route.query, portal } })
}

/**
 * 切换入口。
 *
 * 用户层（:5173）与管理员层（:5174）是两个独立的前端服务，
 * 切换时不是"改一个变量"，而是要整页跳到目标服务，让目标服务加载自己的
 * HTML 入口与路由表。同源时才走 SPA 替换。
 */
function switchPortal(target) {
  if (!['user', 'admin'].includes(target)) return
  const decision = resolvePortalSwitch(target, { query: { ...route.query } })
  if (!decision) return
  error.value = ''
  if (!decision.crossOrigin) {
    form.portal = target
    syncPortalUrl(target)
    return
  }
  // 跨源：整页跳转。目标服务会用 ?portal= 决定默认选中的入口。
  window.location.assign(decision.url)
}

function resetGlassLight() {
  cancelAnimationFrame(glassFrame)
  glassFrame = 0
  glassCard.value?.style.setProperty('--login-light-x', '64%')
  glassCard.value?.style.setProperty('--login-light-y', '8%')
}

function moveGlassLight(event) {
  if (event.pointerType === 'touch' || visualMode.value !== 'balanced' || glassMotionQuery?.matches) return
  // P1：保留 --login-light-x/y 的写入契约（浏览器测试依赖），但降频到约 33Hz，
  // 且 ::before 已改为静态高光、不再引用这两个变量，因此写入不再触发渐变重绘。
  const now = performance.now()
  if (now - lastGlassWriteAt < GLASS_LIGHT_THROTTLE_MS) return
  const bounds = event.currentTarget.getBoundingClientRect()
  glassPointerX = Math.max(0, Math.min(100, (event.clientX - bounds.left) / bounds.width * 100))
  glassPointerY = Math.max(0, Math.min(100, (event.clientY - bounds.top) / bounds.height * 100))
  if (glassFrame) return
  glassFrame = requestAnimationFrame(() => {
    glassFrame = 0
    lastGlassWriteAt = now
    glassCard.value?.style.setProperty('--login-light-x', `${glassPointerX.toFixed(1)}%`)
    glassCard.value?.style.setProperty('--login-light-y', `${glassPointerY.toFixed(1)}%`)
  })
}

watch(visualMode, resetGlassLight)

/* 气泡鼠标视差：仅 balanced 档；rAF 节流写 --bubble-px/py（±18/±14px），
   各气泡按自身 --depth 缩放位移（大泡近动得多，小泡远动得少）。 */
let bubbleFrame = 0
let bubblePointerX = 0
let bubblePointerY = 0
function moveBubbleLight(event) {
  if (event.pointerType === 'touch' || isMobile.value || visualMode.value !== 'balanced' || glassMotionQuery?.matches) return
  // currentTarget 只在派发期间有效：同步读 bounds，rAF 里写 loginShellRef
  const bounds = event.currentTarget.getBoundingClientRect()
  bubblePointerX = Math.max(-1, Math.min(1, (event.clientX - bounds.left) / bounds.width - .5))
  bubblePointerY = Math.max(-1, Math.min(1, (event.clientY - bounds.top) / bounds.height - .5))
  if (bubbleFrame) return
  bubbleFrame = requestAnimationFrame(() => {
    bubbleFrame = 0
    loginShellRef.value?.style.setProperty('--bubble-px', `${(bubblePointerX * 36).toFixed(1)}px`)
    loginShellRef.value?.style.setProperty('--bubble-py', `${(bubblePointerY * 28).toFixed(1)}px`)
  })
}
function resetBubbleLight() {
  cancelAnimationFrame(bubbleFrame)
  bubbleFrame = 0
  loginShellRef.value?.style.setProperty('--bubble-px', '0px')
  loginShellRef.value?.style.setProperty('--bubble-py', '0px')
}
watch(visualMode, resetBubbleLight)

function selectPortal(event) {
  const next = form.portal === 'user' ? 'admin' : 'user'
  switchPortal(next)
  error.value = ''
  // 跨源时页面即将跳转，聚焦目标元素没有意义；同源时才移动焦点。
  if (resolvePortalSwitch(next)?.crossOrigin !== true) {
    event.currentTarget.parentElement.querySelector(`#portal-${next}`)?.focus()
  }
}

watch(() => route.query.portal, (portal) => {
  const next = portal === 'admin' ? 'admin' : 'user'
  if (form.portal !== next) form.portal = next
})

onMounted(() => {
  glassMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  glassMotionQuery.addEventListener('change', resetGlassLight)
  loadPolicy()
  const hint = localStorage.getItem('smartops_login_hint')
  if (hint) {
    form.username = hint
    rememberMe.value = true
  }
  // §8 Gate-2: 监听窗口尺寸变化
  window.addEventListener('resize', updateMobile)
})

// §8 Gate-2: 移动端检测（1024px 断点）
function updateMobile() { isMobile.value = window.innerWidth < 1024 }

onBeforeUnmount(() => {
  cancelAnimationFrame(glassFrame)
  cancelAnimationFrame(bubbleFrame)
  glassMotionQuery?.removeEventListener('change', resetGlassLight)
  window.removeEventListener('resize', updateMobile)
})

async function loadPolicy() {
  policyError.value = ''
  try { policy.value = await registrationPolicy() }
  catch (failure) { policy.value = null; policyError.value = failure.message || '无法读取注册状态，请重试' }
}

function setRegistration(enabled) {
  if (loading.value || (enabled && (form.portal !== 'user' || !policy.value?.enabled))) return
  registering.value = enabled
  form.password = ''
  form.confirmPassword = ''
  showPassword.value = false
  error.value = ''
  success.value = ''
}

async function register() {
  if (form.portal !== 'user' || !policy.value?.enabled) { error.value = '注册已关闭'; return }
  error.value = registrationError(form, policy.value)
  if (error.value) return
  loading.value = true
  try {
    await registerAccount({ ...form, humanToken: humanState.token })
    registering.value = false
    form.portal = 'user'
    await router.replace({ path: '/login', query: { portal: 'user' } })
    success.value = '注册成功，请使用新账号登录。'
  } catch (failure) {
    error.value = failure.message || '注册失败，请稍后重试'
    if (failure.status === 403) await loadPolicy()
    await humanCheck.value?.refresh(failure.status === 428)
  } finally {
    form.password = ''
    form.confirmPassword = ''
    showPassword.value = false
    loading.value = false
  }
}

async function submit() {
  if (loading.value || pendingMfa.value) return
  error.value = ''
  if (!humanState.ready) { error.value = '请先完成安全验证'; return }
  if (registering.value) return register()
  if (!form.username || !form.password) {
    error.value = '请输入账号和密码'
    return
  }
  loading.value = true
  try {
    const user = await loginSession(form.username, form.password, form.portal, humanState.token)
    form.password = ''
    showPassword.value = false
    if (user?.mfaRequired) { pendingMfa.value = user; return }
    await finishLogin(user)
  } catch (failure) {
    error.value = failure.message || '登录失败，请稍后重试'
    await humanCheck.value?.refresh(failure.status === 428)
  } finally { loading.value = false }
}

async function finishLogin(user) {
  try {
    if (rememberMe.value) localStorage.setItem('smartops_login_hint', form.username)
    else localStorage.removeItem('smartops_login_hint')
  } catch {}
  form.password = ''
  await router.replace(sessionLanding(user, route.query.redirect))
}
</script>

<style scoped>
/* ============================================================
   启佑 (Spark You) · 智慧星空 风格覆盖
   只在 .login-shell 局部生效，不影响控制台。
   CanvasAmbientField 通过 palette-root 读这些局部令牌色偏。
   ============================================================ */
.login-shell {
  /* —— 启佑星空局部令牌（CanvasAmbientField 通过 paletteRoot 读这些）—— */
  --smart-bg: #040B16;
  --smart-surface: #081422;
  --smart-primary: #2BA8C8;
  --smart-primary-strong: #7AD7F5;
  --smart-primary-soft: rgba(122, 215, 245, .14);
  --smart-text: #E8F2F7;
  --smart-muted: #6B8BA4;
  --smart-border: color-mix(in srgb, var(--smart-primary-strong) 14%, transparent);
  --smart-border-strong: color-mix(in srgb, var(--smart-primary-strong) 28%, transparent);
  --smart-surface-raised: #0B1A2C;
  /* effect-* 令牌：青绿星云 */
  --smart-effect-primary: #3FB950;
  --smart-effect-strong: #7AD7F5;
  --smart-effect-muted: #6B8BA4;
  --smart-effect-star: #B8EEFF;
  /* —— 玻璃卡视觉参数（启佑：更厚 blur + 青绿高光 + 柔阴影）—— */
  --login-glass-bg: rgba(8, 20, 34, .72);
  --login-glass-edge: rgba(122, 215, 245, .28);
  --login-glass-highlight: rgba(184, 238, 255, .14);
  --login-glass-luster: rgba(122, 215, 245, .08);
  --login-glass-shadow:
    0 30px 72px rgba(0, 0, 0, .32),
    0 8px 24px rgba(43, 168, 200, .06),
    inset 0 1px 0 rgba(184, 238, 255, .24),
    inset 1px 0 0 rgba(122, 215, 245, .10),
    inset 0 -1px 0 rgba(122, 215, 245, .10);
  --login-glass-blur: 14px;
  --login-glyph-edge: rgba(122, 215, 245, .22);
  /* 气泡令牌：泡壁描边 + 左上高光（浅色主题在下方覆盖） */
  --bubble-wall: rgba(122, 215, 245, .38);
  --bubble-wall-faint: rgba(122, 215, 245, .08);
  --bubble-glint: rgba(184, 238, 255, .46);
  position: relative; isolation: isolate;
  /* 启佑极光层 .login-aurora 以 inset:-10% 外扩做漂移，若不裁剪会把
     documentElement.scrollWidth 撑大 20%（login-layout 契约实测 1440→1584）。
     overflow-x:clip 只裁剪、不创建滚动容器，不影响 sticky 与原生 select 弹层。 */
  overflow-x: clip;
  display: flex; flex-direction: column;
  min-height: 100dvh; gap: 28px;
  padding: 24px clamp(20px, 4.4vw, 72px);
  color: var(--smart-text);
  background: var(--smart-bg);
}
/* 亮色启佑：浅蓝星天 + 白玻璃 */
.login-shell[data-theme='light'] {
  --smart-bg: #EAF3FA;
  --smart-surface: #FFFFFF;
  --smart-primary: #1A6E9A;
  --smart-primary-strong: #0E4F7A;
  --smart-text: #0C2535;
  --smart-muted: #46687A;
  --smart-border: color-mix(in srgb, var(--smart-primary-strong) 18%, transparent);
  --smart-border-strong: color-mix(in srgb, var(--smart-primary-strong) 30%, transparent);
  --smart-surface-raised: #F2F8FC;
  --smart-effect-primary: #1A7F37;
  --smart-effect-strong: #0E4F7A;
  --smart-effect-muted: #46687A;
  --smart-effect-star: #2B8AB0;
  --login-glass-bg: rgba(255, 255, 255, .78);
  --login-glass-edge: rgba(14, 79, 122, .24);
  --login-glass-highlight: rgba(255, 255, 255, .90);
  --login-glass-luster: rgba(14, 79, 122, .12);
  --login-glass-shadow:
    0 24px 60px rgba(14, 79, 122, .10),
    inset 0 1px 0 rgba(255, 255, 255, .98),
    inset 1px 0 0 rgba(255, 255, 255, .70),
    inset 0 -1px 0 rgba(14, 79, 122, .10);
  --login-glyph-edge: rgba(14, 79, 122, .18);
  --bubble-wall: rgba(14, 79, 122, .26);
  --bubble-wall-faint: rgba(14, 79, 122, .05);
  --bubble-glint: rgba(255, 255, 255, .85);
}
/* §8 Gate-2: 封面视频槽（封面动态壁纸，balanced 档 + 桌面端才挂载） */
.login-cover-video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; z-index: 0; opacity: 0; transition: opacity .6s ease; pointer-events: none; }
.login-cover-video[src] { opacity: 1; }
/* 静态背景图：深空星海。暗色主题显示（浅色主题保持简洁渐变），
   横向渐变压暗左文案区与右表单区，中间保留最多画面细节。 */
.login-cover-image {
  position: absolute; inset: 0; z-index: 0; pointer-events: none;
  background: url('/assets/login-cover.jpg') center / cover no-repeat;
  opacity: .46;
}
.login-cover-image::after {
  content: ''; position: absolute; inset: 0;
  background:
    linear-gradient(90deg, rgba(4, 11, 22, .66) 0%, rgba(4, 11, 22, .30) 46%, rgba(4, 11, 22, .52) 100%),
    linear-gradient(180deg, rgba(4, 11, 22, .50) 0%, transparent 30%, transparent 68%, rgba(4, 11, 22, .55) 100%);
}
.login-shell[data-theme='light'] .login-cover-image { display: none; }
/* §8 Gate-3: 暗遮罩（40% 深暗，视频层叠用；极光/粒子独立时也提供统一暗度基线） */
.login-cover-mask { position: absolute; inset: 0; z-index: 0; pointer-events: none; background: radial-gradient(ellipse at center, transparent 30%, rgba(4, 11, 22, .40) 100%); }
:global([data-theme='light']) .login-cover-mask { background: radial-gradient(ellipse at center, transparent 30%, rgba(234, 243, 250, .40) 100%); }
.login-shell > .login-ambient { opacity: .42; pointer-events: none; }
.login-shell > .login-meteors { opacity: .3; pointer-events: none; }
/* 启佑极光光带：大尺度缓慢漂移的中景层（方案 §6.2 推荐，零 KB 替代视频层） */
.login-aurora {
  position: absolute; inset: -10%; z-index: 0;
  pointer-events: none; overflow: hidden;
  background:
    radial-gradient(ellipse 60% 40% at 20% 30%, rgba(43, 168, 200, .22), transparent 65%),
    radial-gradient(ellipse 50% 35% at 75% 70%, rgba(63, 185, 80, .14), transparent 60%),
    radial-gradient(ellipse 40% 30% at 50% 50%, rgba(122, 215, 245, .10), transparent 70%);
  background-size: 240% 240%;
  animation: login-aurora-drift 22s ease-in-out infinite alternate;
  filter: blur(20px);
}
/* 第二道光带：冷蓝斜向扫过 */
.login-aurora::after {
  content: ''; position: absolute; inset: -20%;
  background: radial-gradient(ellipse 30% 20% at 80% 20%, rgba(122, 215, 245, .18), transparent 60%);
  background-size: 200% 200%;
  animation: login-aurora-sweep 32s ease-in-out infinite;
}
@keyframes login-aurora-drift {
  0%   { background-position: 0% 0%; transform: translate3d(0, 0, 0); }
  50%  { background-position: 60% 40%; transform: translate3d(-2%, 1%, 0); }
  100% { background-position: 100% 100%; transform: translate3d(1%, -1%, 0); }
}
@keyframes login-aurora-sweep {
  0%, 100% { opacity: .55; transform: translate3d(0, 0, 0); }
  50%      { opacity: 1;    transform: translate3d(-8%, 4%, 0); }
}
/* 启佑亮色：极光换成浅蓝淡绿光带 */
.login-shell[data-theme='light'] .login-aurora {
  background:
    radial-gradient(ellipse 55% 38% at 22% 28%, rgba(26, 110, 154, .18), transparent 65%),
    radial-gradient(ellipse 45% 32% at 72% 68%, rgba(26, 127, 55, .10), transparent 60%),
    radial-gradient(ellipse 38% 28% at 50% 50%, rgba(14, 79, 122, .08), transparent 70%);
}
.login-shell[data-theme='light'] .login-aurora::after {
  background: radial-gradient(ellipse 28% 18% at 78% 22%, rgba(43, 138, 176, .14), transparent 60%);
}
.login-shell[data-visual-mode='lightweight'] .login-aurora,
.login-shell[data-visual-mode='lightweight'] .login-aurora::after { animation-duration: 32s; }
.login-shell:not([data-visual-mode='balanced']) .login-aurora::after { animation: none; opacity: .4; }
@media (prefers-reduced-motion: reduce) { .login-aurora, .login-aurora::after { animation: none; } }
/* 上浮气泡层：零 KB 纯 CSS（radial-gradient 泡壁 + translate3d 上浮），与极光同层纪律 */
.login-bubbles { position: absolute; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; }
.login-bubbles span {
  position: absolute; bottom: -12%;
  border-radius: 50%;
  /* 鼠标视差：--bubble-px/py 由壳层写入，各泡按 --depth 缩放（大泡近、小泡远） */
  --bx: calc(var(--bubble-px, 0px) * var(--depth, .6));
  --by: calc(var(--bubble-py, 0px) * var(--depth, .6));
  /* 泡体 = 左上高光 + 泡壁描边（中心透明，只有边缘一圈），不叠 filter */
  background:
    radial-gradient(circle at 30% 28%, var(--bubble-glint), transparent 42%),
    radial-gradient(circle at 50% 50%, transparent 56%, var(--bubble-wall) 80%, var(--bubble-wall-faint) 100%);
  opacity: 0;
  will-change: transform, opacity;
  animation: login-bubble-rise var(--dur) linear infinite;
  animation-delay: var(--delay);
}
@keyframes login-bubble-rise {
  0%   { transform: translate3d(var(--bx), 0, 0) scale(var(--sc)); opacity: 0; }
  8%   { opacity: var(--op); }
  50%  { transform: translate3d(calc(var(--sway) + var(--bx)), calc(-55vh + var(--by)), 0) scale(calc(var(--sc) * 1.06)); }
  90%  { opacity: var(--op); }
  100% { transform: translate3d(calc(-1 * var(--sway) + var(--bx)), calc(-112vh + var(--by)), 0) scale(var(--sc)); opacity: 0; }
}
/* lightweight：只留前 4 颗 + 周期放慢；reduced-motion / 系统 reduce：气泡静止隐藏 */
.login-shell[data-visual-mode='lightweight'] .login-bubbles span:nth-child(n+5) { display: none; }
.login-shell[data-visual-mode='lightweight'] .login-bubbles span { animation-duration: calc(var(--dur) * 1.4); }
.login-shell[data-visual-mode='reduced-motion'] .login-bubbles { display: none; }
@media (prefers-reduced-motion: reduce) { .login-bubbles span { animation: none; opacity: 0; } }
/* 边缘荧光链路：左右神经走线 + 底部服务拓扑（呼应"维系上下文"）。
   柔和渐变风：走线两端淡出（linearGradient）+ 模糊光晕底层（aura）+ 径向渐变光点，
   无 drop-shadow 硬光。颜色走令牌：明暗主题自动切换（青 = primary-strong，绿 = effect-primary）。 */
.login-traces { position: absolute; z-index: 0; pointer-events: none; opacity: .42; }
.login-traces-defs { position: absolute; width: 0; height: 0; overflow: hidden; pointer-events: none; }
.login-traces--left { left: 0; top: 0; bottom: 72px; width: clamp(56px, 6vw, 104px); }
.login-traces--right { right: 0; top: 0; bottom: 72px; width: clamp(56px, 6vw, 104px); }
.login-traces--bottom { left: 0; right: 0; bottom: 26px; height: 72px; margin-inline: auto; }
/* aura：宽笔触 + blur(8px) 的柔光晕，垫在走线下替代 drop-shadow */
.login-traces__aura { fill: none; stroke: url('#login-trace-fade-cyan'); stroke-width: 6; stroke-linejoin: round; stroke-linecap: round; filter: blur(8px); opacity: .16; }
.login-traces__aura--green { stroke: url('#login-trace-fade-green'); opacity: .13; }
.login-traces__base { fill: none; stroke: url('#login-trace-fade-cyan'); stroke-width: 1.1; stroke-linejoin: round; opacity: .3; }
.login-traces__base--green { stroke: url('#login-trace-fade-green'); }
.login-traces__glow { fill: none; stroke: url('#login-trace-fade-cyan'); stroke-width: 1.1; stroke-linejoin: round; stroke-linecap: round; stroke-dasharray: 12 150; filter: blur(1.8px); opacity: .55; animation: login-trace-flow var(--flow-dur, 5s) linear infinite; }
.login-traces__glow--green { stroke: url('#login-trace-fade-green'); }
.login-traces__node { fill: url('#login-trace-core-cyan'); animation: login-trace-breathe 3s ease-in-out infinite alternate; }
.login-traces__node--green { fill: url('#login-trace-core-green'); animation-duration: 3.8s; }
.login-traces__ring { fill: none; stroke: color-mix(in srgb, var(--smart-primary-strong) 32%, transparent); stroke-width: 1; }
.login-traces__pulse { fill: url('#login-trace-pulse-cyan'); }
.login-traces__pulse--green { fill: url('#login-trace-pulse-green'); }
.login-traces__wire { stroke: url('#login-trace-wire-fade'); stroke-width: 1.1; }
.login-traces__chip { fill: color-mix(in srgb, var(--smart-bg) 82%, transparent); stroke: color-mix(in srgb, var(--smart-primary-strong) 34%, transparent); stroke-width: 1; }
.login-traces__chip-label { font: 9px var(--font-mono); letter-spacing: .08em; fill: var(--smart-muted); }
@keyframes login-trace-flow { to { stroke-dashoffset: -162; } }
@keyframes login-trace-breathe { from { opacity: .45; } to { opacity: 1; } }
/* lightweight：脉冲隐藏、流光/呼吸放慢（走线保持静态可见）；
   reduced-motion 档模板不挂载，系统级 reduce 再兜底关动画。 */
.login-shell[data-visual-mode='lightweight'] .login-traces__pulse { display: none; }
.login-shell[data-visual-mode='lightweight'] .login-traces__glow { animation-duration: calc(var(--flow-dur, 5s) * 1.4); }
@media (prefers-reduced-motion: reduce) { .login-traces__glow, .login-traces__node { animation: none; } }
/* 角落缀饰：与走线同语言——令牌描边 + 既有径向渐变 id，透明度压低不抢主体 */
.login-corner-deco { position: absolute; z-index: 0; pointer-events: none; opacity: .55; }
.login-corner-deco--bl { left: 0; bottom: 0; width: clamp(220px, 21vw, 380px); height: auto; }
.login-corner-deco--br { right: 0; bottom: 0; width: clamp(200px, 19vw, 340px); height: auto; }
.login-corner-deco__arc { fill: none; stroke: color-mix(in srgb, var(--smart-primary-strong) 30%, transparent); stroke-width: 1; }
.login-corner-deco__arc--dashed { stroke-dasharray: 3 7; stroke: color-mix(in srgb, var(--smart-primary-strong) 20%, transparent); }
.login-corner-deco__spoke { stroke: color-mix(in srgb, var(--smart-primary-strong) 16%, transparent); stroke-width: 1; }
.login-corner-deco__constellation { fill: none; stroke: color-mix(in srgb, var(--smart-primary-strong) 34%, transparent); stroke-width: 1; stroke-dasharray: 4 5; }
.login-corner-deco__star { fill: url('#login-trace-core-cyan'); animation: login-trace-breathe 3.4s ease-in-out infinite alternate; }
.login-corner-deco__star--green { fill: url('#login-trace-core-green'); animation-duration: 4.2s; }
.login-corner-deco__tick { stroke: color-mix(in srgb, var(--smart-primary-strong) 26%, transparent); stroke-width: 1; }
.login-corner-deco__orbit { fill: url('#login-trace-pulse-cyan'); }
.login-corner-deco__orbit--green { fill: url('#login-trace-pulse-green'); }
.login-corner-deco__sweep { fill: color-mix(in srgb, var(--smart-primary-strong) 7%, transparent); transform-origin: 100% 100%; animation: login-corner-sweep 22s linear infinite; }
.login-corner-deco__label { font: 9px var(--font-mono); letter-spacing: .1em; fill: color-mix(in srgb, var(--smart-muted) 72%, transparent); }
@keyframes login-corner-sweep { to { transform: rotate(360deg); } }
.login-shell[data-visual-mode='lightweight'] .login-corner-deco__orbit,
.login-shell[data-visual-mode='lightweight'] .login-corner-deco__sweep { display: none; }
.login-shell[data-visual-mode='lightweight'] .login-corner-deco__star { animation: none; }
@media (prefers-reduced-motion: reduce) { .login-corner-deco__sweep, .login-corner-deco__star { animation: none; } }
.login-topbar, .login-layout, .login-page-footer { position: relative; z-index: 1; width: min(100%, 1240px); margin-inline: auto; }
.login-topbar { display: flex; justify-content: space-between; align-items: center; gap: 24px; }
.login-brand { display: flex; align-items: center; gap: 12px; }
.login-brand__mark { display: grid; place-items: center; width: 40px; height: 40px; border: 1px solid var(--smart-border-strong); border-radius: 50%; color: var(--smart-primary-strong); background: var(--smart-surface); }
.login-brand__mark--star { box-shadow: 0 0 0 3px var(--smart-primary-soft); }
.login-brand > div { display: grid; gap: 5px; }
.login-brand strong { font-size: 17px; font-weight: 600; }
.login-brand > div > span { font: 9px var(--font-mono); letter-spacing: .1em; color: var(--smart-muted); }
.login-appearance { display: flex; gap: 16px; }
.login-appearance label { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--smart-muted); }
.login-appearance select { min-height: 44px; max-width: 128px; padding: 0 10px; border: 1px solid var(--smart-border); border-radius: 8px; background: var(--smart-surface); color: var(--smart-text); font-size: 12px; cursor: pointer; }
.login-layout { flex: 1; display: grid; grid-template-columns: minmax(0, 1fr) minmax(380px, 440px); align-items: center; gap: clamp(40px, 5.5vw, 88px); }
.login-showcase { min-width: 0; }
.login-copy { position: relative; z-index: 1; }
/* 品牌徽标：标题上方主视觉（红框位置），柔光投影呼应星空氛围 */
.login-copy__emblem { margin: 0 0 22px; width: 64px; height: 64px; line-height: 0; filter: drop-shadow(0 6px 22px rgba(43, 168, 200, .40)); }
.login-copy__emblem :deep(svg) { width: 100%; height: 100%; }
.editorial-label { margin: 0 0 16px; color: var(--smart-primary-strong); font: 11px var(--font-mono); letter-spacing: .12em; }
.login-copy h1 { margin: 0; font: 500 clamp(36px, 3.7vw, 56px)/1.22 var(--font-cn); letter-spacing: -.025em; text-shadow: none; }
.login-copy h1 span { color: var(--smart-primary-strong); }
.login-copy__description { margin: 20px 0 0; max-width: 440px; color: var(--smart-muted); font-size: 15px; line-height: 1.8; }
.login-organisms { position: relative; isolation: isolate; width: 100%; height: clamp(290px, 35vh, 350px); margin-top: 24px; pointer-events: none; overflow: hidden; border-radius: 16px; }
/* 启佑星云背景：深青径向渐变 */
.login-organisms--spark::before { content: ''; position: absolute; inset: 0; border-radius: inherit; background: radial-gradient(ellipse at 70% 55%, rgba(43, 168, 200, .18) 0%, rgba(63, 185, 80, .08) 40%, transparent 70%); }
/* 启佑星尘粒子：背景层（60 颗） */
.login-stars-bg { position: absolute; inset: 0; border-radius: inherit; background-image:
  radial-gradient(1px 1px at 12% 18%, rgba(184, 238, 255, .55), transparent 50%),
  radial-gradient(1px 1px at 34% 72%, rgba(122, 215, 245, .45), transparent 50%),
  radial-gradient(1px 1px at 56% 26%, rgba(184, 238, 255, .48), transparent 50%),
  radial-gradient(1px 1px at 78% 58%, rgba(122, 215, 245, .52), transparent 50%),
  radial-gradient(1px 1px at 88% 16%, rgba(184, 238, 255, .42), transparent 50%),
  radial-gradient(1px 1px at 22% 88%, rgba(63, 185, 80, .38), transparent 50%),
  radial-gradient(1.5px 1.5px at 68% 82%, rgba(184, 238, 255, .60), transparent 50%),
  radial-gradient(1px 1px at 44% 42%, rgba(122, 215, 245, .40), transparent 50%);
  background-size: 100% 100%;
  animation: login-stars-twinkle 6s ease-in-out infinite alternate;
}
/* 启佑星尘：前景层（稍亮，位置微偏移） */
.login-stars-front { position: absolute; inset: 0; border-radius: inherit; background-image:
  radial-gradient(1.2px 1.2px at 18% 42%, rgba(255, 255, 255, .70), transparent 50%),
  radial-gradient(1px 1px at 48% 66%, rgba(184, 238, 255, .55), transparent 50%),
  radial-gradient(1.4px 1.4px at 72% 30%, rgba(255, 255, 255, .60), transparent 50%),
  radial-gradient(1px 1px at 92% 78%, rgba(122, 215, 245, .50), transparent 50%),
  radial-gradient(1.1px 1.1px at 6% 64%, rgba(184, 238, 255, .48), transparent 50%);
  animation: login-stars-twinkle 4.5s ease-in-out infinite alternate-reverse;
}
@keyframes login-stars-twinkle {
  from { opacity: .6; }
  to { opacity: 1; }
}
.login-scene-label { position: absolute; bottom: 0; left: 0; font: 10px var(--font-mono); color: var(--smart-muted); letter-spacing: .12em; }
.login-trust { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 24px 0 0; padding-top: 18px; border-top: 1px solid var(--smart-border); }
.login-trust > div { display: grid; gap: 6px; }
.login-trust dt { color: var(--smart-muted); font-size: 12px; }
.login-trust dd { margin: 0; color: var(--smart-text); font-size: 13px; }
.login-form { position: relative; isolation: isolate; overflow: hidden; display: grid; gap: 13px; width: 100%; min-width: 0; padding: 26px; border: 1px solid var(--login-glass-edge); border-radius: 14px 14px 14px 14px / 13px 13px 15px 15px; background: var(--login-glass-bg); box-shadow: var(--login-glass-shadow); backdrop-filter: blur(var(--login-glass-blur)) saturate(120%); -webkit-backdrop-filter: blur(var(--login-glass-blur)) saturate(120%); }
.login-form::before, .login-form::after { content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none; z-index: 0; }
.login-form::before { background: radial-gradient(ellipse 70% 55% at 50% -10%, var(--login-glass-highlight), transparent 72%), linear-gradient(145deg, var(--login-glass-luster), transparent 36%); opacity: .55; }
.login-form::after { background: linear-gradient(180deg, var(--login-glass-highlight), transparent 18%, transparent 82%, var(--login-glass-luster)); opacity: .16; animation: none; }
.login-form > * { position: relative; z-index: 1; }
.login-form__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.login-form__header .editorial-label { margin-bottom: 12px; font-size: 10px; letter-spacing: .06em; }
.login-form__header h2 { margin: 0 0 6px; font-size: 27px; font-weight: 550; line-height: 1.2; color: var(--smart-text); }
.login-form__header p:not(.editorial-label) { margin: 0; color: var(--smart-muted); font-size: 13px; line-height: 1.6; }
.login-form__status { display: inline-flex; align-items: center; gap: 6px; margin-top: 2px; color: var(--smart-primary-strong); font: 9px var(--font-mono); letter-spacing: .06em; }
.login-form__status > span { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.role-switcher { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; padding: 4px; border: 1px solid var(--smart-border); border-radius: 11px; background: var(--smart-bg); }
.role-switcher button { display: flex; justify-content: center; align-items: center; gap: 8px; min-height: 40px; padding: 8px; border: 1px solid transparent; border-radius: 7px; background: var(--smart-surface); color: var(--smart-muted); font-size: 13px; }
.role-switcher button.is-active { border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); font-weight: 600; }
.role-switcher__dot { width: 6px; height: 6px; border: 1px solid currentColor; border-radius: 50%; }
.role-switcher button.is-active .role-switcher__dot { background: currentColor; }
.role-switcher__hint { margin: 8px 0 0; color: var(--smart-muted); font-size: 11.5px; line-height: 1.6; }
.role-switcher__hint code { padding: 1px 5px; border-radius: 4px; background: var(--smart-primary-soft); color: var(--smart-primary-strong); font-family: var(--font-mono); font-size: 11px; }
.login-form__fields { display: grid; gap: 16px; }
.login-field { display: grid; gap: 8px; min-width: 0; }
.login-field__label { color: var(--smart-text); font-size: 13px; font-weight: 500; }
.login-input-shell { display: flex; align-items: center; position: relative; min-width: 0; border: 1px solid var(--smart-border-strong); border-radius: 9px; background: var(--smart-surface); }
.login-input-shell:focus-within { border-color: var(--smart-primary-strong); box-shadow: 0 0 0 3px var(--smart-primary-soft); }
.login-input-icon { position: absolute; left: 13px; color: var(--smart-muted); font-size: 16px; pointer-events: none; }
.login-input-shell input { width: 100%; min-width: 0; min-height: 44px; padding: 0 44px 0 40px; border: 0; outline: none; background: transparent; color: var(--smart-text); border-radius: inherit; font: 14px var(--font-cn); }
.login-input-shell input::placeholder { color: var(--smart-muted); opacity: 1; }
.password-visibility-toggle { position: absolute; right: 2px; top: 2px; display: grid; place-items: center; width: 44px; height: 44px; padding: 0; border: 0; border-radius: 7px; background: transparent; color: var(--smart-muted); }
.password-visibility-toggle:hover { color: var(--smart-primary-strong); }
.login-form__options { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.remember-control { position: relative; display: flex; align-items: center; gap: 8px; min-height: 32px; color: var(--smart-muted); font-size: 12px; cursor: pointer; }
.remember-control input { width: 16px; height: 16px; margin: 0; accent-color: var(--smart-primary); cursor: pointer; }
.login-form__policy { color: var(--smart-muted); font-size: 11px; line-height: 1.6; }
.login-form__error, .login-form__notice { margin: 0; padding: 10px 12px; border: 1px solid var(--smart-border-strong); border-radius: 8px; background: var(--smart-bg); color: var(--smart-text); font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
.login-form__error { border-color: var(--smart-danger); color: var(--smart-danger); }
.login-submit { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; min-height: 46px; padding: 12px 16px; border: 1px solid transparent; border-radius: 9px; background: var(--smart-primary); color: var(--smart-accent-foreground); font: 600 14px var(--font-cn); }
.login-submit:hover:not(:disabled) { background: var(--smart-primary-strong); }
.login-submit__spinner { width: 16px; height: 16px; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: login-spin .8s linear infinite; }
.login-registration { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 0 6px; color: var(--smart-muted); font-size: 13px; }
.login-registration button { min-height: 36px; padding: 4px; border: 0; border-radius: 4px; background: var(--smart-surface); color: var(--smart-primary-strong); font-size: 13px; text-decoration: underline; text-underline-offset: 4px; }
.login-registration p { flex-basis: 100%; margin: 6px 0 0; line-height: 1.6; text-align: center; overflow-wrap: anywhere; }
.login-form__guidance { margin: 0; color: var(--smart-muted); font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
/* 浅色主题玻璃卡叠加后，纯 --smart-muted 前景仅 3.61:1（login-layout 契约要求 ≥4.5:1）。
   混入主文本色后在明暗主题下都达标，同时保留比正文略弱一级的层级。 */
.login-form__footer { margin: 0; padding-top: 12px; border-top: 1px solid var(--smart-border); color: color-mix(in srgb, var(--smart-text) 85%, var(--smart-muted)); font-size: 11px; line-height: 1.7; text-align: center; }
.login-form button:disabled { cursor: not-allowed; opacity: .65; }
.login-form :is(button, input):focus-visible, .login-appearance select:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 3px; }
.login-form .login-input-shell input:focus-visible { outline: none; }
.login-page-footer { display: flex; justify-content: space-between; gap: 16px; color: var(--smart-muted); font: 10px var(--font-mono); letter-spacing: .06em; }
@keyframes login-spin { to { transform: rotate(360deg); } }
@media (max-width: 1100px) {
  .login-shell { gap: 24px; }
  .login-traces { display: none; }
  .login-layout { flex: none; grid-template-columns: minmax(0, 1fr); width: min(100%, 540px); gap: 24px; }
  .login-showcase { display: grid; grid-template-columns: minmax(0, 1fr) 170px; align-items: center; gap: 12px; }
  .login-copy .editorial-label { margin-bottom: 12px; font-size: 10px; }
  .login-copy__emblem { width: 48px; height: 48px; margin-bottom: 14px; }
  .login-copy h1 { font-size: 30px; }
  .login-copy__description, .login-trust, .login-scene-label { display: none; }
  .login-organisms { width: 100%; height: 170px; margin: 0; }
  .login-form { width: min(100%, 480px); margin-inline: auto; }
  .login-page-footer { margin-top: auto; }
}
@media (max-width: 600px) {
  .login-shell { --login-glass-blur: 8px; gap: 20px; padding: 20px 16px; }
  .login-topbar { flex-wrap: wrap; gap: 16px; }
  .login-brand > div > span { font-size: 8px; }
  .login-appearance { width: 100%; gap: 12px; }
  .login-appearance label { flex: 1; }
  .login-appearance select { flex: 1; max-width: none; min-width: 0; }
  .login-showcase { grid-template-columns: minmax(0, 1fr) 112px; gap: 8px; }
  .login-copy__emblem { width: 40px; height: 40px; margin-bottom: 10px; }
  .login-copy h1 { font-size: clamp(21px, 6vw, 26px); }
  .login-copy .editorial-label { font-size: 9px; margin-bottom: 8px; }
  .login-organisms { height: 128px; }
  .login-layout { gap: 16px; }
  .login-form { gap: 16px; padding: 24px 20px; border-radius: 12px; }
  .login-form__header h2 { font-size: 27px; }
  .login-form__status { font-size: 8px; }
  .login-page-footer { font-size: 9px; flex-wrap: wrap; }
}
.login-shell[data-visual-mode='lightweight'], .login-shell[data-visual-mode='reduced-motion'] { --login-glass-blur: 6px; }
.login-shell:not([data-visual-mode='balanced']) .login-form::after { animation: none; }
@media (pointer: coarse) { .login-form::after { animation: none; } }
@media (prefers-reduced-motion: reduce) { .login-submit__spinner, .login-form::after { animation: none; } .login-form, .login-submit { transition: none; } }
.login-shell[data-visual-mode='reduced-motion'] .login-submit__spinner { animation: none; }
/* 启佑简化：星尘粒子在 reduced-motion 下关闭闪烁 */
@media (prefers-reduced-motion: reduce) { .login-stars-bg, .login-stars-front { animation: none; } }
.login-scene-label { display: none; }
.login-trust { grid-template-columns: 1fr; gap: 8px; margin-top: 18px; padding-top: 14px; }
.login-trust > div:not(:first-child) { display: none; }
.login-trust > div { display: flex; align-items: baseline; gap: 10px; }
.login-copy__description { max-width: 380px; font-size: 14px; line-height: 1.7; }
/* 卡片聚焦反馈统一由 global.css 的 .login-form 规则负责（含 reduced-motion 关闭）；
   这里只保留按钮的按压缩放，卡片几何恒为 transform: none。 */
.login-submit { transition: transform 180ms cubic-bezier(.22, 1.3, .36, 1), background-color 160ms ease; }
.login-submit:active { transform: scale(.985); }
.login-organisms::before { opacity: .55; }
.login-form { gap: 12px; }
.login-form__header h2 { font-size: 24px; }
@supports not (backdrop-filter: blur(1px)) { .login-form { background: var(--smart-surface); } }
</style>
