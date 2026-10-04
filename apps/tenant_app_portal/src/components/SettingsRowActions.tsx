import ContainerRowActions from '@/components/ContainerRowActions'

export interface SettingsRowActionsProps {
  onEdit?: () => void
  editDisabled?: boolean
  editHidden?: boolean
  editTitle?: string
  onDelete?: () => void
  deleteDisabled?: boolean
  deleteHidden?: boolean
  deleteTitle?: string
}

/** Ghost icon edit/delete actions for Settings record-list tables. */
export default function SettingsRowActions(props: SettingsRowActionsProps) {
  return <ContainerRowActions {...props} />
}
