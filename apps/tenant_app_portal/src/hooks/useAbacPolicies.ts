import { useCallback, useState } from 'react'

import {
  createPolicy,
  deletePolicy,
  disablePolicy,
  enablePolicy,
  listPolicies,
  seedPolicies,
  simulatePolicy,
  updatePolicy,
  type AbacPolicy,
  type AbacPolicyCreatePayload,
  type AbacPolicyUpdatePayload,
  type ResourceType,
  type SimulatePolicyPayload,
  type SimulatePolicyResponse,
  type SeedPoliciesResponse,
} from '@/lib/abacPolicyApi'

export function useAbacPolicies(resourceType?: ResourceType) {
  const [policies, setPolicies] = useState<AbacPolicy[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchPolicies = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listPolicies(resourceType)
      setPolicies(data)
      return data
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to fetch policies'
      setError(msg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [resourceType])

  const createOne = useCallback(async (payload: AbacPolicyCreatePayload): Promise<AbacPolicy> => {
    const policy = await createPolicy(payload)
    setPolicies((prev) => [...prev, policy])
    return policy
  }, [])

  const updateOne = useCallback(
    async (id: number, payload: AbacPolicyUpdatePayload): Promise<AbacPolicy> => {
      const updated = await updatePolicy(id, payload)
      setPolicies((prev) => prev.map((p) => (p.id === id ? updated : p)))
      return updated
    },
    []
  )

  const removeOne = useCallback(async (id: number): Promise<void> => {
    await deletePolicy(id)
    setPolicies((prev) => prev.filter((p) => p.id !== id))
  }, [])

  const toggleStatus = useCallback(async (id: number, enable: boolean): Promise<AbacPolicy> => {
    const updated = enable ? await enablePolicy(id) : await disablePolicy(id)
    setPolicies((prev) => prev.map((p) => (p.id === id ? updated : p)))
    return updated
  }, [])

  const seed = useCallback(async (): Promise<SeedPoliciesResponse> => {
    const result = await seedPolicies()
    await fetchPolicies()
    return result
  }, [fetchPolicies])

  return {
    policies,
    loading,
    error,
    fetchPolicies,
    createOne,
    updateOne,
    removeOne,
    toggleStatus,
    seed,
  }
}

export function useSimulatePolicy() {
  const [result, setResult] = useState<SimulatePolicyResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async (payload: SimulatePolicyPayload) => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await simulatePolicy(payload)
      setResult(res)
      return res
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Simulation failed'
      setError(msg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  return { result, loading, error, run }
}
