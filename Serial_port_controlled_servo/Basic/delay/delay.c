#include "delay.h"

#define AHB_INPUT  72  // 请按RCC配置的AHB时钟频率填写这里（单位MHz）

void delay_init(void)
{
    /* SysTick时钟源 = HCLK = 72MHz，无须额外初始化 */
}

void delay_us(uint32_t uS)
{
    // uS微秒级延时函数（参考值：在时钟72MHz时，最大值233015）
    SysTick->LOAD = AHB_INPUT * uS;       // 装载重装值
    SysTick->VAL  = 0x00;                 // 清除计数器
    SysTick->CTRL = 0x00000005;           // 时钟源HCLK，打开定时器
    while (!(SysTick->CTRL & 0x00010000)); // 等待计数到0
    SysTick->CTRL = 0x00000004;           // 关闭定时器
}

void delay_ms(uint16_t ms)
{
    // mS毫秒级延时函数
    while (ms-- != 0) {
        delay_us(1000);
    }
}

void delay_s(uint16_t s)
{
    // S秒级延时函数
    while (s-- != 0) {
        delay_ms(1000);
    }
}
