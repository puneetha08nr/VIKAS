'use client'

import { Suspense, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'

function Spinner() {
  return (
    <div className="flex h-screen items-center justify-center">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
    </div>
  )
}

function CallbackHandler() {
  const router = useRouter()
  const searchParams = useSearchParams()

  useEffect(() => {
    const code = searchParams.get('code')
    const error = searchParams.get('error')
    const errorDescription = searchParams.get('error_description')

    if (error) {
      router.replace(`/login?error=${encodeURIComponent(errorDescription ?? error)}`)
      return
    }

    if (!code) {
      router.replace('/login')
      return
    }

    supabase.auth.exchangeCodeForSession(code).then(({ error: exchangeError }) => {
      if (exchangeError) {
        router.replace(`/login?error=${encodeURIComponent(exchangeError.message)}`)
      } else {
        router.replace('/keywords')
      }
    })
  }, [router, searchParams])

  return <Spinner />
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <CallbackHandler />
    </Suspense>
  )
}
