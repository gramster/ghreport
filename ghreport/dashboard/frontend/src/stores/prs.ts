import { defineStore } from 'pinia'
import axios from 'axios'

interface PrItem {
  number: number
  title: string
  state: string
  created_by: string
  closed_by: string | null
  created_at: string | null
  merged_at: string | null
  closed_at: string | null
  lines_changed: number
  files_changed: number
}

interface PrResponse {
  total: number
  page: number
  per_page: number
  pull_requests: PrItem[]
}

export const usePrsStore = defineStore('prs', {
  state: () => ({
    prs: [] as PrItem[],
    total: 0,
    page: 1,
    perPage: 50,
    loading: false,
    stateFilter: null as string | null,
  }),
  actions: {
    async fetchPrs(owner: string, repo: string) {
      this.loading = true
      try {
        const params: Record<string, string | number> = {
          page: this.page,
          per_page: this.perPage,
        }
        if (this.stateFilter) params.state = this.stateFilter
        const { data } = await axios.get<PrResponse>(
          `/api/repos/${owner}/${repo}/prs`,
          { params },
        )
        this.prs = data.pull_requests
        this.total = data.total
      } finally {
        this.loading = false
      }
    },
  },
})
