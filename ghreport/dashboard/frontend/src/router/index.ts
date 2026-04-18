import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/DashboardHome.vue'),
    },
    {
      path: '/repo/:owner/:repo',
      name: 'repo-detail',
      component: () => import('@/views/RepoDetail.vue'),
      props: true,
    },
    {
      path: '/repo/:owner/:repo/revisits',
      name: 'issue-revisits',
      component: () => import('@/views/IssueRevisits.vue'),
      props: true,
    },
    {
      path: '/repo/:owner/:repo/pr-activity',
      name: 'pr-activity',
      component: () => import('@/views/PrActivity.vue'),
      props: true,
    },
    {
      path: '/repo/:owner/:repo/closed',
      name: 'closed-issues',
      component: () => import('@/views/ClosedIssues.vue'),
      props: true,
    },
    {
      path: '/repo/:owner/:repo/insights',
      name: 'insights',
      component: () => import('@/views/Insights.vue'),
      props: true,
    },
    {
      path: '/repos',
      name: 'repositories',
      component: () => import('@/views/Repositories.vue'),
    },
    {
      path: '/team',
      name: 'team',
      component: () => import('@/views/TeamMembers.vue'),
    },
    {
      path: '/member/:login',
      name: 'member-detail',
      component: () => import('@/views/MemberDetail.vue'),
      props: true,
    },
  ],
})

export default router
