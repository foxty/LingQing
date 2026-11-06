export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Returns first password complexity error message key segment, or null if valid. */
export function validateNewUserPasswordComplexity(
  password: string,
  translate: (key: string) => string
): string | null {
  if (password.length < 8) {
    return translate('settings.usersTab.newUser.passwordMinLength')
  }
  if (!/[A-Z]/.test(password)) {
    return translate('settings.usersTab.newUser.passwordRequireUppercase')
  }
  if (!/[a-z]/.test(password)) {
    return translate('settings.usersTab.newUser.passwordRequireLowercase')
  }
  if (!/\d/.test(password)) {
    return translate('settings.usersTab.newUser.passwordRequireDigit')
  }
  return null
}
