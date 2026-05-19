// Polling hook — fetches immediately, then every intervalMs.
// Uses request sequencing to prevent stale responses from overwriting fresh ones.

import { useState, useEffect, useRef } from 'react'
import { request } from '../api'

export default function usePolling(url, { intervalMs = 3000, enabled = true } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const seqRef = useRef(0)

  useEffect(() => {
    if (!enabled) {
      setIsLoading(false)
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
          setIsLoading(false)
          // Schema-verified field names: tick, status (always present)
          console.log('[poll]', { tick: json.tick, status: json.status })
        }
      } catch (e) {
        if (e.name === 'AbortError') return
        if (mounted && seq === seqRef.current) {
          setError(e.message)
          setIsLoading(false)
        }
      }
    }

    setIsLoading(true)
    fetchData()
    timer = setInterval(fetchData, intervalMs)

    return () => {
      mounted = false
      clearInterval(timer)
    }
  }, [url, intervalMs, enabled])

  return { data, error, isLoading }
}
