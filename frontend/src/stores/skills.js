import { defineStore } from 'pinia'
import { SKILL_KEY, emptySkills, decodeSkills, installSkill, skillPrompt } from '../domain/skills/workspace.ts'
export const useSkillsStore = defineStore('skills', {
  state: () => ({ workspace: emptySkills(), loaded: false, error: '' }),
  getters: { enabled: state => state.workspace.skills.filter(item => item.enabled) },
  actions: {
    load() { if (this.loaded) return; try { this.workspace = decodeSkills(localStorage.getItem(SKILL_KEY)) } catch { this.error = '技能存储无法读取，原内容未覆盖。' } this.loaded = true },
    save(next) { skillPrompt(next); localStorage.setItem(SKILL_KEY, JSON.stringify(next)); this.workspace = next; this.error = '' },
    install(markdown, source) { this.save(installSkill(this.workspace, markdown, source)) },
    toggle(id) { this.save({ ...this.workspace, skills: this.workspace.skills.map(item => item.id === id ? { ...item, enabled: !item.enabled } : item) }) },
    remove(id) { this.save({ ...this.workspace, skills: this.workspace.skills.filter(item => item.id !== id) }) },
    goal(value) { if (value.length > 2000) throw new Error('目标不能超过 2000 字符。'); this.save({ ...this.workspace, goal: value }) },
    prompt() { return skillPrompt(this.workspace) }
  }
})
