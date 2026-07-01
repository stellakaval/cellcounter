import { supabase } from '../lib/supabase'

export default function LoginPage() {
  const handleGoogleLogin = async () => {
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    })
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 w-80 text-center space-y-6">
        <div>
          <h1 className="text-2xl font-bold mb-1">Cellcounter</h1>
          <p className="text-sm text-gray-400">AI-powered nucleus counting</p>
        </div>
        <button
          onClick={handleGoogleLogin}
          className="w-full py-3 px-4 bg-white text-gray-900 rounded-xl font-medium text-sm hover:bg-gray-100 transition-colors flex items-center justify-center gap-3"
        >
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
            <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
            <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
            <path fill="#FBBC05" d="M3.964 10.706A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.706V4.962H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.038l3.007-2.332z"/>
            <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.962L3.964 6.294C4.672 4.169 6.656 3.58 9 3.58z"/>
          </svg>
          Sign in with Google
        </button>
        <p className="text-xs text-gray-600">For authorized lab members only</p>
      </div>
    </div>
  )
}
