import { useState, useEffect, useRef } from 'react'

export default function usePolling(url, intervalMs = 3000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true

    async function fetchData() {
      try {
        const res = await fetch(url)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const json = await res.json()
        if (mountedRef.current) {
          setData(json)
          setError(null)
          setLoading(false)
        }
      } catch (e) {
        if (mountedRef.current) {
          setError(e.message)
          setLoading(false)
        }
      }
    }

    fetchData()
    const timer = setInterval(fetchData, intervalMs)

    return () => {
      mountedRef.current = false
      clearInterval(timer)
    }
  }, [url, intervalMs])

  return { data, error, loading }
}
