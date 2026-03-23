import { ref, computed } from 'vue'

const projects = ref([])
const currentProjectId = ref(null)

export function useProject() {
  const currentProject = computed(() =>
    projects.value.find((p) => p.id === currentProjectId.value) || null
  )

  function setProjects(list) {
    projects.value = list
  }

  function setCurrentProjectId(id) {
    currentProjectId.value = id
  }

  function addProject(project) {
    projects.value = [project, ...projects.value]
  }

  function removeProject(projectId) {
    projects.value = projects.value.filter((p) => p.id !== projectId)
  }

  function updateProjectInList(updated) {
    const idx = projects.value.findIndex((p) => p.id === updated.id)
    if (idx !== -1) {
      projects.value = [
        ...projects.value.slice(0, idx),
        { ...projects.value[idx], ...updated },
        ...projects.value.slice(idx + 1),
      ]
    }
  }

  return {
    projects,
    currentProjectId,
    currentProject,
    setProjects,
    setCurrentProjectId,
    addProject,
    removeProject,
    updateProjectInList,
  }
}
