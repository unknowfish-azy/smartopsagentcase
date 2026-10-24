import { defineStore } from 'pinia'
import { createFaultEvent, createInvestigationContext } from '../domain/investigation/faultEvent.ts'
import { questionsForFault } from '../domain/investigation/inquiry.ts'

export const useInvestigationStore = defineStore('investigation', {
  state: () => ({ faultEvents: [], activeContext: null, history: [] }),
  getters: {
    activeFault: state => state.activeContext?.faultEvent || null,
    hasActiveInvestigation: state => Boolean(state.activeContext)
  },
  actions: {
    detect(input) {
      const event = createFaultEvent(input)
      if (this.activeContext) this.history = [this.activeContext, ...this.history].slice(0, 50)
      this.faultEvents = [event, ...this.faultEvents.filter(item => item.id !== event.id)]
      this.activeContext = createInvestigationContext(event)
      this.activeContext.questions = questionsForFault(event)
      this.activeContext.state = 'WAITING_USER'
      return event
    },
    setState(nextState) {
      if (!this.activeContext) return
      this.activeContext = { ...this.activeContext, state: nextState, updatedAt: new Date().toISOString() }
    },
    addObservation(observation) {
      if (!this.activeContext || !observation) return
      this.activeContext.observations.push(observation)
      this.activeContext.updatedAt = new Date().toISOString()
    },
    addKnowledgeReference(reference) {
      if (!this.activeContext || !reference?.documentId) return
      const record = { ...reference, retrievedAt: reference.retrievedAt || new Date().toISOString() }
      const index = this.activeContext.knowledgeReferences.findIndex(item => item.documentId === record.documentId)
      if (index >= 0) this.activeContext.knowledgeReferences.splice(index, 1, record)
      else this.activeContext.knowledgeReferences.push(record)
      this.activeContext.updatedAt = new Date().toISOString()
    },
    addAnswer(answer) {
      if (!this.activeContext || !answer?.questionId) return
      const record = { ...answer, answeredAt: answer.answeredAt || new Date().toISOString() }
      const index = this.activeContext.answers.findIndex(item => item.questionId === record.questionId)
      if (index >= 0) this.activeContext.answers.splice(index, 1, record)
      else this.activeContext.answers.push(record)
      this.activeContext.updatedAt = new Date().toISOString()
    },
    addHypothesis(hypothesis) {
      if (!this.activeContext || !hypothesis?.id) return
      const index = this.activeContext.hypotheses.findIndex(item => item.id === hypothesis.id)
      if (index >= 0) this.activeContext.hypotheses.splice(index, 1, hypothesis)
      else this.activeContext.hypotheses.push(hypothesis)
      this.activeContext.updatedAt = new Date().toISOString()
    },
    close() { this.activeContext = null }
  }
})
