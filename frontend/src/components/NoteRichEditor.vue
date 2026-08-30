<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import { uploadToCloudinary } from '../cloudinary.js'
import { extractNoteImageUrls, noteBodyToHtml } from '../noteContent.js'

const props = defineProps({
  modelValue: { type: String, default: '' },
  imageUrls: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'update:imageUrls', 'error'])
const fileInput = ref(null)
const imageUploading = ref(false)

const editor = useEditor({
  content: noteBodyToHtml(props.modelValue, props.imageUrls),
  extensions: [
    StarterKit.configure({
      heading: { levels: [2, 3] },
      link: {
        openOnClick: false,
        autolink: true,
        defaultProtocol: 'https',
        HTMLAttributes: { target: '_blank', rel: 'noopener noreferrer' },
      },
    }),
    Image.configure({
      allowBase64: false,
      HTMLAttributes: { loading: 'lazy' },
    }),
  ],
  editorProps: {
    attributes: {
      class: 'note-rich-editor__content',
      'aria-label': 'ノート本文',
    },
  },
  onUpdate: ({ editor: currentEditor }) => {
    const html = currentEditor.isEmpty ? '' : currentEditor.getHTML()
    emit('update:modelValue', html)
    emit('update:imageUrls', extractNoteImageUrls(html))
  },
})

watch(() => props.modelValue, value => {
  if (!editor.value) return
  const html = noteBodyToHtml(value, props.imageUrls)
  if (editor.value.getHTML() !== html) {
    editor.value.commands.setContent(html, { emitUpdate: false })
  }
})

onBeforeUnmount(() => editor.value?.destroy())

function buttonClass(active) {
  return ['note-editor-button', { 'note-editor-button--active': active }]
}

function editLink() {
  if (!editor.value) return
  const previousUrl = editor.value.getAttributes('link').href || ''
  const url = window.prompt('リンク先URLを入力してください', previousUrl)
  if (url === null) return
  if (!url.trim()) {
    editor.value.chain().focus().extendMarkRange('link').unsetLink().run()
    return
  }
  editor.value.chain().focus().extendMarkRange('link').setLink({ href: url.trim() }).run()
}

async function onImageFiles(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length || !editor.value) return

  const currentCount = extractNoteImageUrls(editor.value.getHTML()).length
  if (currentCount + files.length > 10) {
    emit('error', '画像は1つのノートにつき10枚までです')
    return
  }

  imageUploading.value = true
  emit('error', '')
  try {
    for (const file of files) {
      if (!file.type.startsWith('image/')) throw new Error('画像ファイルを選択してください')
      const url = await uploadToCloudinary(file)
      editor.value.chain().focus().setImage({ src: url, alt: file.name || 'ノート画像' }).run()
    }
  } catch (error) {
    emit('error', error.message)
  } finally {
    imageUploading.value = false
  }
}
</script>

<template>
  <div class="note-rich-editor">
    <div v-if="editor" class="note-rich-editor__toolbar" role="toolbar" aria-label="本文の書式設定">
      <button type="button" :class="buttonClass(editor.isActive('paragraph'))" title="本文" @click="editor.chain().focus().setParagraph().run()">本文</button>
      <button type="button" :class="buttonClass(editor.isActive('heading', { level: 2 }))" title="大見出し" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">見出し</button>
      <button type="button" :class="buttonClass(editor.isActive('heading', { level: 3 }))" title="小見出し" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">小見出し</button>
      <span class="note-editor-divider"></span>
      <button type="button" :class="buttonClass(editor.isActive('bold'))" title="太字" @click="editor.chain().focus().toggleBold().run()"><i class="ti ti-bold"></i></button>
      <button type="button" :class="buttonClass(editor.isActive('italic'))" title="斜体" @click="editor.chain().focus().toggleItalic().run()"><i class="ti ti-italic"></i></button>
      <button type="button" :class="buttonClass(editor.isActive('underline'))" title="下線" @click="editor.chain().focus().toggleUnderline().run()"><i class="ti ti-underline"></i></button>
      <span class="note-editor-divider"></span>
      <button type="button" :class="buttonClass(editor.isActive('bulletList'))" title="箇条書き" @click="editor.chain().focus().toggleBulletList().run()"><i class="ti ti-list"></i></button>
      <button type="button" :class="buttonClass(editor.isActive('orderedList'))" title="番号付きリスト" @click="editor.chain().focus().toggleOrderedList().run()"><i class="ti ti-list-numbers"></i></button>
      <button type="button" :class="buttonClass(editor.isActive('blockquote'))" title="引用" @click="editor.chain().focus().toggleBlockquote().run()"><i class="ti ti-blockquote"></i></button>
      <button type="button" :class="buttonClass(editor.isActive('link'))" title="リンク" @click="editLink"><i class="ti ti-link"></i></button>
      <span class="note-editor-divider"></span>
      <button type="button" class="note-editor-button note-editor-button--image" :disabled="imageUploading" title="現在位置へ画像を挿入" @click="fileInput?.click()">
        <i class="ti ti-photo-plus"></i><span>{{ imageUploading ? '送信中…' : '画像' }}</span>
      </button>
      <input ref="fileInput" class="visually-hidden" type="file" accept="image/*" multiple @change="onImageFiles" />
      <span class="note-editor-toolbar-spacer"></span>
      <button type="button" class="note-editor-button" :disabled="!editor.can().undo()" title="元に戻す" @click="editor.chain().focus().undo().run()"><i class="ti ti-arrow-back-up"></i></button>
      <button type="button" class="note-editor-button" :disabled="!editor.can().redo()" title="やり直す" @click="editor.chain().focus().redo().run()"><i class="ti ti-arrow-forward-up"></i></button>
    </div>
    <EditorContent :editor="editor" />
    <div class="note-rich-editor__help">
      画像はカーソル位置へ入ります。画像を選択してDeleteキーで削除、ドラッグで位置を移動できます（最大10枚）。
    </div>
  </div>
</template>

<style>
.note-rich-editor {
  overflow: hidden;
  border: 1px solid #ced4da;
  border-radius: 10px;
  background: #fff;
}
.note-rich-editor:focus-within {
  border-color: #86b7fe;
  box-shadow: 0 0 0 .2rem rgba(13, 110, 253, .15);
}
.note-rich-editor__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 8px;
  border-bottom: 1px solid #dee2e6;
  background: #f8f9fa;
}
.note-editor-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-width: 34px;
  min-height: 34px;
  padding: 5px 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #364152;
  font-size: .82rem;
}
.note-editor-button:hover:not(:disabled) { background: #e9ecef; }
.note-editor-button:disabled { opacity: .4; }
.note-editor-button--active {
  border-color: #99d9d0;
  background: #d9f3ef;
  color: #126b60;
}
.note-editor-button--image {
  border-color: #b8ded9;
  background: #e8f7f5;
  color: #126b60;
}
.note-editor-divider {
  width: 1px;
  height: 26px;
  margin: 0 2px;
  background: #d6dadd;
}
.note-editor-toolbar-spacer { flex: 1; }
.note-rich-editor__content {
  min-height: 300px;
  padding: 18px;
  outline: none;
  line-height: 1.75;
}
.note-rich-editor__content > *:first-child { margin-top: 0; }
.note-rich-editor__content > *:last-child { margin-bottom: 0; }
.note-rich-editor__content h2 { margin: 1.2em 0 .55em; font-size: 1.45rem; }
.note-rich-editor__content h3 { margin: 1.1em 0 .5em; font-size: 1.18rem; }
.note-rich-editor__content blockquote {
  margin: 1em 0;
  padding: .2em 1em;
  border-left: 4px solid #2d9c8f;
  color: #56606d;
}
.note-rich-editor__content img {
  display: block;
  width: auto;
  max-width: 100%;
  max-height: 560px;
  margin: 14px auto;
  border-radius: 10px;
  object-fit: contain;
  cursor: grab;
}
.note-rich-editor__content img.ProseMirror-selectednode {
  outline: 3px solid rgba(45, 156, 143, .45);
}
.note-rich-editor__content a { color: #0d6efd; text-decoration: underline; }
.note-rich-editor__content p.is-editor-empty:first-child::before {
  float: left;
  height: 0;
  color: #9aa1a9;
  content: '本文を入力してください';
  pointer-events: none;
}
.note-rich-editor__help {
  padding: 7px 12px;
  border-top: 1px solid #eef0f2;
  color: #6c757d;
  background: #fbfcfc;
  font-size: .76rem;
}
@media (max-width: 575.98px) {
  .note-rich-editor__toolbar { gap: 3px; padding: 6px; }
  .note-editor-button { min-width: 32px; min-height: 32px; padding: 4px 6px; }
  .note-editor-divider { display: none; }
  .note-rich-editor__content { min-height: 260px; padding: 14px; }
}
</style>
