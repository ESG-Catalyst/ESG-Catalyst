import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './en.json'
import ar from './ar.json'

/**
 * Initialize i18n in the SAME language the UI store persisted (under
 * `esg-ui-prefs`). The store applies `dir`/`lang` to <html> eagerly on load;
 * without reading the same value here, i18n would stay on English while the
 * page flipped to RTL — the "Arabic doesn't switch on the Home page" bug.
 */
function getInitialLang(): 'en' | 'ar' {
  if (typeof window === 'undefined') return 'en'
  try {
    const raw = localStorage.getItem('esg-ui-prefs')
    if (raw) {
      const parsed = JSON.parse(raw) as { state?: { language?: unknown } }
      const l = parsed?.state?.language
      if (l === 'ar' || l === 'en') return l
    }
  } catch {
    /* fall through to default */
  }
  return 'en'
}

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    ar: { translation: ar },
  },
  lng: getInitialLang(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export default i18n
