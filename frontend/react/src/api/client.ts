import axios from 'axios'

export const apiClient = axios.create({
  headers: { 'Content-Type': 'application/json' },
})

// Inject auth token on every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('esg_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  if (import.meta.env.DEV) {
    console.debug(`[API] ${config.method?.toUpperCase()} ${config.url}`)
  }
  return config
})

// 401 → redirect to login
apiClient.interceptors.response.use(
  (res) => {
    if (import.meta.env.DEV) {
      console.debug(`[API] ${res.status} ${res.config.url}`)
    }
    return res
  },
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('esg_token')
      window.location.replace('/auth/login')
    }
    return Promise.reject(err)
  },
)

export default apiClient
