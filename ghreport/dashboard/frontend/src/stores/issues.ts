import { defineStore } from 'pinia'
import axios from 'axios'

interface IssueItem {
  number: number
  title: string
  state: string
  created_by: string
  closed_by: string | null
  created_at: string | null
  closed_at: string | null
  first_team_response_at: string | null
  last_team_response_at: string | null
  event_count: number
}

interface IssueResponse {
  total: number
  page: number
  per_page: number
  issues: IssueItem[]
}

export const useIssuesStore = defineStore('issues', {
  state: () => ({
    issues: [] as IssueItem[],
    total: 0,
    page: 1,
    perPage: 50,
    loading: false,
    stateFilter: null as string | null,
  }),
  actions: {
    async fetchIssues(owner: string, repo: string) {
      this.loading = true
      try {
        const params: Record<string, string | number> = {
          page: this.page,
          per_page: this.perPage,
        }
        if (this.stateFilter) params.state = this.stateFilter
        const { data } = await axios.get<IssueResponse>(
          `/api/repos/${owner}/${repo}/issues`,
          { params },
        )
        this.issues = data.issues
        this.total = data.total
      } finally {
        this.loading = false
      }
    },
  },
})
