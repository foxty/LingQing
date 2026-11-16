/** Collection form validation — limits mirror apps/shared/document/constants.py */
import * as z from 'zod'

export const DOCUMENT_COLLECTION_NAME_MAX_LENGTH = 120
export const DOCUMENT_COLLECTION_DESCRIPTION_MAX_LENGTH = 500

export function buildCollectionFormSchema(messages: {
  nameRequired: string
  nameTooLong: string
  descriptionTooLong: string
}) {
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, messages.nameRequired)
      .max(DOCUMENT_COLLECTION_NAME_MAX_LENGTH, messages.nameTooLong),
    description: z
      .string()
      .trim()
      .max(DOCUMENT_COLLECTION_DESCRIPTION_MAX_LENGTH, messages.descriptionTooLong),
  })
}

export type CollectionFormSchema = z.infer<ReturnType<typeof buildCollectionFormSchema>>