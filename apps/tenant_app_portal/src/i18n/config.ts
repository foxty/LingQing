import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import en from './locales/en/translation.json'
import zh from './locales/zh/translation.json'

const resources = {
  en: { translation: en },
  zh: { translation: zh },
}

function syncDocumentI18n(lng: string = i18n.language) {
  const isZh = lng.startsWith('zh')
  document.documentElement.lang = isZh ? 'zh-CN' : 'en'
  document.title = i18n.t('brand.pageTitle')
  document
    .querySelector('meta[name="description"]')
    ?.setAttribute('content', i18n.t('brand.pageDescription'))
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'zh',
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
    interpolation: {
      escapeValue: false,
    },
  })
  .then(() => syncDocumentI18n())

i18n.on('languageChanged', syncDocumentI18n)

export default i18n
