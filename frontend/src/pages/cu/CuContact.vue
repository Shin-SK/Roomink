<script setup>
import LayoutCustomer from '../../components/LayoutCustomer.vue'
</script>

<template>
  <LayoutCustomer>
    <h2 class="page-title mb-4">お問い合わせ</h2>

    <div class="card mb-4">
      <div class="card-header">
        <i class="ti ti-message-circle"></i> よくあるご質問
      </div>
      <div class="card-body">
        <div class="accordion" id="faqAccordion">
          <div class="accordion-item">
            <h2 class="accordion-header">
              <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#faq1">
                予約のキャンセルはできますか？
              </button>
            </h2>
            <div id="faq1" class="accordion-collapse collapse" data-bs-parent="#faqAccordion">
              <div class="accordion-body">
                予約の24時間前までにご連絡いただければキャンセル可能です。
              </div>
            </div>
          </div>
          <div class="accordion-item">
            <h2 class="accordion-header">
              <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#faq2">
                予約の変更はできますか？
              </button>
            </h2>
            <div id="faq2" class="accordion-collapse collapse" data-bs-parent="#faqAccordion">
              <div class="accordion-body">
                日時やコースの変更はお電話にて承っております。
              </div>
            </div>
          </div>
          <div class="accordion-item">
            <h2 class="accordion-header">
              <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#faq3">
                支払い方法を教えてください
              </button>
            </h2>
            <div id="faq3" class="accordion-collapse collapse" data-bs-parent="#faqAccordion">
              <div class="accordion-body">
                現金またはクレジットカードがご利用いただけます。
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-header">
        <i class="ti ti-phone"></i> お電話でのお問い合わせ
      </div>
      <div class="card-body text-center">
        <p class="mb-3">お急ぎの場合やご不明点がございましたら、お気軽にお電話ください。</p>
        <a href="tel:03-1234-5678" class="btn btn-outline-primary btn-lg">
          <i class="ti ti-phone"></i> 03-1234-5678
        </a>
        <p class="text-muted small mt-2 mb-0">営業時間: 12:00〜22:00</p>
      </div>
    </div>
  </LayoutCustomer>
</template>
