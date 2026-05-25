import { useState, useEffect } from 'react'
import { useSettings as useApiSettings, useUpdateSettings, useResetSettings } from '@/hooks/useApi'
import type { AppSettings } from '@/types/index'

export function useSettings() {
  const { data, isLoading } = useApiSettings()
  const updateMutation = useUpdateSettings()
  const resetMutation = useResetSettings()
  const [localSettings, setLocalSettings] = useState<AppSettings>({})

  useEffect(() => {
    if (data) setLocalSettings(data)
  }, [data])

  const update = (key: string, value: unknown) => {
    setLocalSettings((prev) => ({ ...prev, [key]: value }))
  }

  const save = async () => {
    await updateMutation.mutateAsync(localSettings)
  }

  const reset = async () => {
    await resetMutation.mutateAsync()
  }

  return {
    settings: localSettings,
    isLoading,
    update,
    save,
    reset,
    isSaving: updateMutation.isPending,
    isResetting: resetMutation.isPending,
  }
}
