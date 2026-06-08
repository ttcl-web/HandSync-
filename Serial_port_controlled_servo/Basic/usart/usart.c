#include "usart.h"
#include "sys.h"

/* ==================== 接收环形缓冲区 ==================== */
#define RX_BUF_SIZE  128

static volatile u8   rx_buf[RX_BUF_SIZE];       // 环形缓冲区
static volatile u16  rx_head = 0;                // 写指针 (ISR)
static volatile u16  rx_tail = 0;                // 读指针 (main)
static volatile u16  rx_overflow = 0;            // 溢出计数

/* ==================== printf 重定向 ==================== */
struct __FILE
{
    int handle;
};
FILE __stdout;

void _sys_exit(int x)
{
    x = x;
}

int fputc(int ch, FILE *f)
{
    while ((USART1->SR & 0x40) == 0) {}
    USART1->DR = (u8)ch;
    return ch;
}

/* ==================== printf 封装 ==================== */
void USART1_printf(char *fmt, ...)
{
    char buffer[USART1_REC_LEN + 1];
    va_list arg_ptr;
    va_start(arg_ptr, fmt);
    vsnprintf(buffer, USART1_REC_LEN + 1, fmt, arg_ptr);
    va_end(arg_ptr);
    for (u8 i = 0; i < strlen(buffer); i++) {
        USART_SendData(USART1, (u8)buffer[i]);
        while (USART_GetFlagStatus(USART1, USART_FLAG_TC) == RESET) {}
    }
}

/* ==================== 初始化 ==================== */
void USART1_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStructure;
    USART_InitTypeDef USART_InitStructure;
    NVIC_InitTypeDef NVIC_InitStructure;

    RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1 | RCC_APB2Periph_GPIOA, ENABLE);

    /* PA9 = TX (复用推挽) */
    GPIO_InitStructure.GPIO_Pin   = GPIO_Pin_9;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_AF_PP;
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    /* PA10 = RX (浮空输入) */
    GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_10;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    /* 中断配置 */
    NVIC_InitStructure.NVIC_IRQChannel                   = USART1_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 3;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority        = 3;
    NVIC_InitStructure.NVIC_IRQChannelCmd                = ENABLE;
    NVIC_Init(&NVIC_InitStructure);

    /* UART 参数: 115200, 8N1 */
    USART_InitStructure.USART_BaudRate            = 115200;
    USART_InitStructure.USART_WordLength          = USART_WordLength_8b;
    USART_InitStructure.USART_StopBits            = USART_StopBits_1;
    USART_InitStructure.USART_Parity              = USART_Parity_No;
    USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
    USART_InitStructure.USART_Mode                = USART_Mode_Rx | USART_Mode_Tx;
    USART_Init(USART1, &USART_InitStructure);

    USART_ITConfig(USART1, USART_IT_RXNE, ENABLE);
    USART_Cmd(USART1, ENABLE);
}

/* ==================== 中断服务：写入环形缓冲区 ==================== */
void USART1_IRQHandler(void)
{
    if (USART_GetITStatus(USART1, USART_IT_RXNE) != RESET)
    {
        u8 byte = (u8)USART_ReceiveData(USART1);
        u16 next = (rx_head + 1) % RX_BUF_SIZE;
        if (next != rx_tail)          // 未满
        {
            rx_buf[rx_head] = byte;
            rx_head = next;
        }
        else
        {
            rx_overflow++;            // 丢弃但计数
        }
    }
}

/* ==================== 供 main 调用的 API ==================== */

/* 读取一个字节，返回 1=成功, 0=缓冲区空 */
u8 UART_ReadByte(u8 *out)
{
    if (rx_tail == rx_head) return 0;  // 空
    u16 next = (rx_tail + 1) % RX_BUF_SIZE;
    *out   = rx_buf[rx_tail];
    rx_tail = next;
    return 1;
}

/* 获取溢出次数并清零 */
u16 UART_GetOverflow(void)
{
    u16 n = rx_overflow;
    rx_overflow = 0;
    return n;
}
