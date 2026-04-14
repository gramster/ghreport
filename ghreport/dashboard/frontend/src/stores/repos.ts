import { defineStore } from 'pinia'
import axios from 'axios'

interface RepoSummary {
  owner: string
  name: string
  last_synced_at: string | null
  issues: Record<string, number>
  pull_requests: Record<string, number>
}

export const useReposStore = defineStore('repos', {
  state: () => ({
    repos: [] as RepoSummary[],
    loading: false,
  }),
  actions: {
    async fetchRepos() {
      this.loading = true
      try {
        const { data } = await axios.get<RepoSummary[]>('/api/repos')
        this.repos = data
      } finally {
        this.loading = false
      }
    },
  },
})
