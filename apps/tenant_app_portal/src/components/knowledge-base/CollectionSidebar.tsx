import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import TagChips from '@/components/TagChips'
import type { DocumentCollection } from '@/lib/documentCollectionsApi'
import type { TagKeyDTO, TagValueDTO } from '@/lib/tagsApi'
import { FolderOpen, Plus, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface CollectionSidebarProps {
  collections: DocumentCollection[]
  filteredCollections: DocumentCollection[]
  isLoading: boolean
  selectedCollectionId?: number
  collectionSearch: string
  showCollectionSearch: boolean
  canUpload: boolean
  canReadTags: boolean
  tagKeys: TagKeyDTO[]
  collectionTagsMap: Record<number, TagValueDTO[]>
  onCollectionSearchChange: (value: string) => void
  onSelectCollection: (collectionId: number) => void
  onCreateCollection: () => void
}

export default function CollectionSidebar({
  collections,
  filteredCollections,
  isLoading,
  selectedCollectionId,
  collectionSearch,
  showCollectionSearch,
  canUpload,
  canReadTags,
  tagKeys,
  collectionTagsMap,
  onCollectionSearchChange,
  onSelectCollection,
  onCreateCollection,
}: CollectionSidebarProps) {
  const { t } = useTranslation()

  return (
    <aside className="rounded-lg border bg-card p-3 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-medium">{t('knowledgeBase.collections')}</h2>
        {canUpload && (
          <Button variant="ghost" size="sm" className="h-7 px-2" onClick={onCreateCollection}>
            <Plus className="w-4 h-4" />
          </Button>
        )}
      </div>

      {showCollectionSearch && (
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={collectionSearch}
            onChange={(e) => onCollectionSearchChange(e.target.value)}
            placeholder={t('knowledgeBase.searchCollections')}
            className="h-8 pl-8 text-sm"
          />
        </div>
      )}

      {isLoading ? (
        <p className="text-xs text-muted-foreground px-2 py-1">{t('common.loading')}</p>
      ) : collections.length === 0 ? (
        <div className="px-2 py-4 space-y-3 text-center">
          <p className="text-sm text-muted-foreground">{t('knowledgeBase.noCollections')}</p>
          {canUpload && (
            <Button size="sm" variant="outline" className="w-full" onClick={onCreateCollection}>
              <Plus className="w-4 h-4 mr-2" />
              {t('knowledgeBase.newCollection')}
            </Button>
          )}
        </div>
      ) : filteredCollections.length === 0 ? (
        <p className="text-xs text-muted-foreground px-2 py-1">{t('common.noResults')}</p>
      ) : (
        <div className="space-y-1">
          {filteredCollections.map((collection) => (
            <button
              key={collection.id}
              type="button"
              onClick={() => onSelectCollection(collection.id)}
              className={`w-full rounded-md px-2 py-2 text-left text-sm ${
                selectedCollectionId === collection.id
                  ? 'bg-accent text-accent-foreground'
                  : 'hover:bg-muted'
              }`}
            >
              <div className="flex items-start gap-2">
                <FolderOpen className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate flex-1">{collection.name}</span>
                    <span className="text-xs text-muted-foreground tabular-nums shrink-0">
                      {collection.document_count}
                    </span>
                  </div>
                  {canReadTags && (collectionTagsMap[collection.id]?.length || 0) > 0 ? (
                    <TagChips
                      tags={collectionTagsMap[collection.id]}
                      tagKeys={tagKeys}
                      compact
                      maxVisible={2}
                    />
                  ) : null}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </aside>
  )
}
