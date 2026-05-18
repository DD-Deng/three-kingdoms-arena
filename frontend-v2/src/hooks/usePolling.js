import { useState, useEffect, useRef } from 'react'
import { request } from '../api'

export default function usePolling(url, intervalMs = 3000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const seqRef = useRef(0)

  useEffect(() => {
    // null interval → stop polling, keep existing state
    if (intervalMs == null) {
      setLoading(false)
      return
    }

    let mounted = true
    let timer = null

    async function fetchData() {
      const seq = ++seqRef.current

      try {
        const json = await request(url)
        if (mounted && seq === seqRef.current) {
          setData(json)
          setError(null)
          setLoading(false)
        }
      } catch (e) {
        if (e.name === 'AbortError') return
        if (mounted && seq === seqRef.current) {
          setError(e.message)
          setLoading(false)
        }
      }
    }

    setLoading(true)
    fetchData()
    timer = setInterval(fetchData, intervalMs)

    return () => {
      mounted = false
      clearInterval(timer)
    }
  }, [url, intervalMs])

  return { data, error, loading }
}
