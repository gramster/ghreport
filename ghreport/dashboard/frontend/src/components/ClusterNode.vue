<template>
  <div :class="level === 0 ? 'cluster-card' : 'subcluster-card'">
    <div class="cluster-header">
      <strong :class="level > 0 ? 'subcluster-name' : ''">{{ cluster.name }}</strong>
      <span class="cluster-count">{{ cluster.issues.length }} issues</span>
    </div>
    <p v-if="cluster.summary" class="cluster-summary">{{ cluster.summary }}</p>

    <template v-if="cluster.subclusters && cluster.subclusters.length">
      <ClusterNode
        v-for="(sub, idx) in cluster.subclusters"
        :key="`${level}-${idx}-${sub.name}`"
        :cluster="sub"
        :owner="owner"
        :repo="repo"
        :issue-titles="issueTitles"
        :level="level + 1"
      />
    </template>

    <details v-else class="cluster-details">
      <summary>Show issues</summary>
      <ul class="cluster-issue-list">
        <li v-for="num in cluster.issues" :key="num">
          <a :href="`https://github.com/${owner}/${repo}/issues/${num}`" target="_blank">#{{ num }}</a>
          <span class="issue-title">{{ issueTitles[num] || '' }}</span>
        </li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
interface ClusterNodeModel {
  name: string
  issues: number[]
  summary: string
  subclusters?: ClusterNodeModel[]
}

defineProps<{
  cluster: ClusterNodeModel
  owner: string
  repo: string
  issueTitles: Record<number, string>
  level: number
}>()
</script>

<style scoped>
.cluster-card {
  border: 1px solid #e1e4e8;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin-bottom: 0.75rem;
}
.subcluster-card {
  border: 1px solid #eaeef2;
  border-radius: 5px;
  padding: 0.5rem 0.75rem;
  margin: 0.4rem 0 0.4rem 0.75rem;
  background: #f9fafb;
}
.cluster-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.3rem;
}
.subcluster-name {
  font-size: 0.88rem;
}
.cluster-count {
  font-size: 0.8rem;
  color: #586069;
  background: #f1f3f5;
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
}
.cluster-summary {
  color: #586069;
  font-size: 0.9rem;
  margin: 0.25rem 0 0.5rem;
}
.cluster-details {
  margin-top: 0.4rem;
}
.cluster-details summary {
  cursor: pointer;
  font-size: 0.85rem;
  color: #0366d6;
  user-select: none;
}
.cluster-details summary:hover {
  text-decoration: underline;
}
.cluster-issue-list {
  list-style: none;
  padding-left: 0.25rem;
  margin: 0.4rem 0 0;
}
.cluster-issue-list li {
  margin-bottom: 0.3rem;
  font-size: 0.85rem;
  line-height: 1.4;
}
.cluster-issue-list a {
  color: #0366d6;
  text-decoration: none;
  font-weight: 600;
  margin-right: 0.4rem;
}
.cluster-issue-list a:hover {
  text-decoration: underline;
}
.issue-title {
  color: #24292e;
}
</style>
