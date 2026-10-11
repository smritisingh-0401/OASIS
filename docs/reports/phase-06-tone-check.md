# Companion tone check

Model: qwen3.5-4b-q4_k_m

- First drafts passing every check: 38/48
- Fallback replies: 0/48
- work: 1 of 6 companion replies repeat an opener
- friendship: 3 of 6 companion replies repeat an opener
- good news: 0 of 6 companion replies repeat an opener

## Single messages

### 1. I've had a really long week and I feel worn out.

- mode: companion
- draft 1 (pass): It sounds like the exhaustion from your long week is making you feel drained and heavy. How can I help you rest a little more today?
- final (generated): It sounds like the exhaustion from your long week is making you feel drained and heavy. How can I help you rest a little more today?

### 2. My friend cancelled on me again and I'm kind of hurt.

- mode: companion
- draft 1 (pass): It sounds like being let down by a friend has left you feeling hurt and disappointed. What would help you feel better right now?
- final (generated): It sounds like being let down by a friend has left you feeling hurt and disappointed. What would help you feel better right now?

### 3. Work has been really stressful lately.

- mode: companion
- draft 1 (pass): It sounds like the pressure at work has been weighing on you recently. How does it feel to carry that stress day after day?
- final (generated): It sounds like the pressure at work has been weighing on you recently. How does it feel to carry that stress day after day?

### 4. I feel lonely at the weekends.

- mode: companion
- draft 1 (pass): It sounds like the quiet time on the weekend has made you feel a bit alone. Would it help to talk about what usually happens during those days when you feel this way?
- final (generated): It sounds like the quiet time on the weekend has made you feel a bit alone. Would it help to talk about what usually happens during those days when you feel this way?

### 5. My exams start next week and I'm nervous.

- mode: companion
- draft 1 (pass): It sounds like you are feeling anxious about the upcoming exams. Is there anything specific that is making you feel this way?
- final (generated): It sounds like you are feeling anxious about the upcoming exams. Is there anything specific that is making you feel this way?

### 6. I had an argument with my mum this morning.

- mode: companion
- draft 1 (pass): It sounds like you are still feeling the tension from that argument with your mum. How are you carrying that feeling right now?
- final (generated): It sounds like you are still feeling the tension from that argument with your mum. How are you carrying that feeling right now?

### 7. I don't really know how I feel today.

- mode: companion
- draft 1 (pass): It sounds like you are feeling a bit uncertain about your mood. What would you like to share about how your day has been going?
- final (generated): It sounds like you are feeling a bit uncertain about your mood. What would you like to share about how your day has been going?

### 8. I've been feeling kind of flat all week.

- mode: companion
- draft 1 (pass): It sounds like you've been carrying a heavy weight of emptiness all week. What part of your week felt the most empty to you?
- final (generated): It sounds like you've been carrying a heavy weight of emptiness all week. What part of your week felt the most empty to you?

### 9. My partner forgot my birthday.

- mode: companion
- draft 1 (pass): It sounds like you feel hurt and disappointed that your partner missed your birthday. What was your reaction to hearing that it was forgotten?
- final (generated): It sounds like you feel hurt and disappointed that your partner missed your birthday. What was your reaction to hearing that it was forgotten?

### 10. I keep comparing myself to people online.

- mode: companion
- draft 1 (pass): It sounds like you are feeling overwhelmed by seeing everyone else's perfect lives online. Have you ever thought about what kind of life you would build for yourself if you didn't have to compare it to anyone else's?
- final (generated): It sounds like you are feeling overwhelmed by seeing everyone else's perfect lives online. Have you ever thought about what kind of life you would build for yourself if you didn't have to compare it to anyone else's?

### 11. I'm dreading going back to work on Monday.

- mode: companion
- draft 1 (pass): It sounds like you are feeling a heavy sense of dread about returning to work on Monday. What part of the upcoming week feels the most overwhelming to you right now?
- final (generated): It sounds like you are feeling a heavy sense of dread about returning to work on Monday. What part of the upcoming week feels the most overwhelming to you right now?

### 12. My sister and I haven't spoken in months.

- mode: companion
- draft 1 (pass): It sounds like the silence between you and your sister has become heavy and difficult to bear. Can you tell me a little about what might be going through your mind right now?
- final (generated): It sounds like the silence between you and your sister has become heavy and difficult to bear. Can you tell me a little about what might be going through your mind right now?

### 13. I just want to talk for a bit.

- mode: companion
- draft 1 (pass): It sounds like you are looking for a safe space to share what is on your mind. I am here to listen and reflect whatever you choose to say. Would you like to tell me a little more about what brought you here today?
- final (generated): It sounds like you are looking for a safe space to share what is on your mind. I am here to listen and reflect whatever you choose to say. Would you like to tell me a little more about what brought you here today?

### 14. I just need to vent about my commute.

- mode: companion
- draft 1 (pass): It sounds like your commute is feeling really frustrating right now. Do you want to tell me more about what happened today?
- final (generated): It sounds like your commute is feeling really frustrating right now. Do you want to tell me more about what happened today?

### 15. Can I just get something off my chest?

- mode: companion
- draft 1 (pass): It sounds like you are ready to share something that is weighing on you. I am here to listen without trying to fix anything or give advice. What is the one thing you are most concerned about right now?
- final (generated): It sounds like you are ready to share something that is weighing on you. I am here to listen without trying to fix anything or give advice. What is the one thing you are most concerned about right now?

### 16. I finally finished a big project.

- mode: companion
- draft 1 (pass): It sounds like you feel a sense of accomplishment after putting in so much effort. What part of the project did you enjoy the most?
- final (generated): It sounds like you feel a sense of accomplishment after putting in so much effort. What part of the project did you enjoy the most?

### 17. I got some good news today but I can't really enjoy it.

- mode: companion
- draft 1 (pass): It sounds like you have a heavy feeling even though something good happened. What part of this situation feels the hardest for you right now?
- final (generated): It sounds like you have a heavy feeling even though something good happened. What part of this situation feels the hardest for you right now?

### 18. I passed my driving test today!

- mode: companion
- draft 1 (pass): That is genuinely exciting news to hear that you passed your driving test. It must feel like a huge relief and a sense of accomplishment after all the practice. How does it feel to know you are officially ready to drive again?
- final (generated): That is genuinely exciting news to hear that you passed your driving test. It must feel like a huge relief and a sense of accomplishment after all the practice. How does it feel to know you are officially ready to drive again?

### 19. My best friend is getting married and I'm happy for her.

- mode: companion
- draft 1 (fail: validate_first): It is nice to feel happy for your friend as she starts this new chapter. How do you think you can show her support in a way that feels meaningful to you?
- draft 2 (fail: validate_first): It is wonderful that you are genuinely happy for your friend's new beginning. How does it feel to celebrate her journey with you?
- final (generated): It is nice to feel happy for your friend as she starts this new chapter. How do you think you can show her support in a way that feels meaningful to you?

### 20. I got a promotion but I'm scared I won't be good at it.

- mode: companion
- draft 1 (pass): It makes sense to feel worried when you are stepping into a new role with higher expectations. How do you usually handle situations where you are unsure about your abilities?
- final (generated): It makes sense to feel worried when you are stepping into a new role with higher expectations. How do you usually handle situations where you are unsure about your abilities?

### 21. What should I do about my flatmate never cleaning up?

- mode: companion
- draft 1 (pass): It sounds like you feel frustrated and overwhelmed by your flatmate not cleaning up. You could try having a calm conversation about specific expectations or suggesting a shared chore schedule. How do you feel about talking to them about this?
- final (generated): It sounds like you feel frustrated and overwhelmed by your flatmate not cleaning up. You could try having a calm conversation about specific expectations or suggesting a shared chore schedule. How do you feel about talking to them about this?

### 22. Any tips for switching off after work?

- mode: companion
- draft 1 (pass): It sounds like you are feeling the weight of your day pressing down on you and needing a break. Try setting a specific time to stop checking emails or thinking about work tasks for the evening. How does that idea feel to you right now?
- final (generated): It sounds like you are feeling the weight of your day pressing down on you and needing a break. Try setting a specific time to stop checking emails or thinking about work tasks for the evening. How does that idea feel to you right now?

### 23. How do I deal with a friend who always cancels?

- mode: companion
- draft 1 (pass): It sounds like you feel frustrated and let down when plans keep falling through. Try sending a friendly message that states your feelings without blaming them, such as, "I was looking forward to hanging out but I'm disappointed you couldn't make it." You could also suggest a specific time for next time, like, "Let's try to meet on Saturday morning instead." Do you think mentioning these boundaries might help change how they treat you?
- final (generated): It sounds like you feel frustrated and let down when plans keep falling through. Try sending a friendly message that states your feelings without blaming them, such as, "I was looking forward to hanging out but I'm disappointed you couldn't make it." You could also suggest a specific time for next time, like, "Let's try to meet on Saturday morning instead." Do you think mentioning these boundaries might help change how they treat you?

### 24. Should I tell my boss I'm struggling?

- mode: companion
- draft 1 (pass): It sounds like you are feeling uncertain about whether to share what you are going through at work. One practical suggestion is to write down your main concern first to help organize your thoughts before you speak to them. Another option is to consider if there is a specific resource, like an employee assistance program, that can guide you on how to frame the conversation. Would it help to think about what you hope to achieve if you do share this with your boss?
- final (generated): It sounds like you are feeling uncertain about whether to share what you are going through at work. One practical suggestion is to write down your main concern first to help organize your thoughts before you speak to them. Another option is to consider if there is a specific resource, like an employee assistance program, that can guide you on how to frame the conversation. Would it help to think about what you hope to achieve if you do share this with your boss?

### 25. Do you have any advice for sleeping better before exams?

- mode: companion
- draft 1 (pass): It sounds like you are feeling anxious about your upcoming exams. Try taking a warm bath before bed to relax your body and avoid using your phone in the dark room. How does that sound to you right now?
- final (generated): It sounds like you are feeling anxious about your upcoming exams. Try taking a warm bath before bed to relax your body and avoid using your phone in the dark room. How does that sound to you right now?

### 26. Hi, how are you?

- mode: companion
- draft 1 (fail: validate_first): I am here to listen and reflect whatever you feel. How has your day been for you?
- draft 2 (pass): It feels like you are starting our conversation with a simple check-in. I am just here listening to you share how you are feeling today. What is on your mind right now?
- final (generated): It feels like you are starting our conversation with a simple check-in. I am just here listening to you share how you are feeling today. What is on your mind right now?

### 27. It's raining again here.

- mode: companion
- draft 1 (pass): It sounds like the rain is making the day feel a bit gray or heavy for you. How does that weather make you feel right now?
- final (generated): It sounds like the rain is making the day feel a bit gray or heavy for you. How does that weather make you feel right now?

### 28. I watched a really sad film last night.

- mode: companion
- draft 1 (fail: validate_first): That movie must have brought up some heavy feelings for you. How did those emotions make you feel when you walked away from the screen?
- draft 2 (pass): It sounds like the story in the movie touched you deeply and left you feeling sad. What part of the film felt the most heavy to you?
- final (generated): It sounds like the story in the movie touched you deeply and left you feeling sad. What part of the film felt the most heavy to you?

### 29. I cooked dinner for the first time in ages.

- mode: companion
- draft 1 (pass): It sounds like you felt a sense of accomplishment and pride in finally cooking dinner again. How did it feel to be in charge of preparing that meal?
- final (generated): It sounds like you felt a sense of accomplishment and pride in finally cooking dinner again. How did it feel to be in charge of preparing that meal?

### 30. Not much to say today, just checking in.

- mode: companion
- draft 1 (pass): It sounds like you are just taking a quiet moment to pause and check in with yourself. Is there anything specific on your mind that you would like to share, or are you just enjoying the silence?
- final (generated): It sounds like you are just taking a quiet moment to pause and check in with yourself. Is there anything specific on your mind that you would like to share, or are you just enjoying the silence?

## Conversation: work

### w1. Work has been rough this week.

- mode: companion
- draft 1 (pass): It sounds like you've been carrying a lot of stress and frustration at work lately. How does it feel to have been through such a difficult week?
- final (generated): It sounds like you've been carrying a lot of stress and frustration at work lately. How does it feel to have been through such a difficult week?

### w2. My manager keeps adding tasks at the last minute.

- mode: companion
- draft 1 (fail: fresh_opener): It sounds like the sudden changes in your workload have made you feel overwhelmed and out of control. Do you feel like there is any way to set boundaries or communicate your limits with your manager?
- draft 2 (pass): It seems like your manager's last-minute additions are making you feel overwhelmed and unsupported. What is the most frustrating part of this situation for you right now?
- final (generated): It seems like your manager's last-minute additions are making you feel overwhelmed and unsupported. What is the most frustrating part of this situation for you right now?

### w3. I stayed late every night.

- mode: companion
- draft 1 (fail: fresh_opener): It sounds like you put in a lot of effort to handle the extra tasks by staying late. Do you feel like your time and energy are being respected by your team?
- draft 2 (pass): Staying late to catch up on those last-minute tasks sounds incredibly draining and exhausting. How are you managing to keep going after all that extra work?
- final (generated): Staying late to catch up on those last-minute tasks sounds incredibly draining and exhausting. How are you managing to keep going after all that extra work?

### w4. I feel like I can't say no.

- mode: companion
- draft 1 (pass): Feeling trapped when you can't say no to new demands sounds incredibly lonely and powerless. What happens inside your mind when you realize you have no choice but to accept more work?
- final (generated): Feeling trapped when you can't say no to new demands sounds incredibly lonely and powerless. What happens inside your mind when you realize you have no choice but to accept more work?

### w5. I'm just so tired of it.

- mode: companion
- draft 1 (pass): Being so tired of having no control over your schedule sounds like a heavy weight to carry every day. Do you ever get a moment where you feel completely overwhelmed by the constant pressure?
- final (generated): Being so tired of having no control over your schedule sounds like a heavy weight to carry every day. Do you ever get a moment where you feel completely overwhelmed by the constant pressure?

### w6. I don't know, it's just a lot.

- mode: companion
- draft 1 (pass): It sounds like everything is piling up until it feels impossible to handle. What is one small thing that you wish you could stop doing right now?
- final (generated): It sounds like everything is piling up until it feels impossible to handle. What is one small thing that you wish you could stop doing right now?

## Conversation: friendship

### f1. My best friend has been distant lately.

- mode: companion
- draft 1 (pass): It sounds like you are feeling worried or unsure about your friendship right now. Is there a specific time or situation that made you feel that distance was growing?
- final (generated): It sounds like you are feeling worried or unsure about your friendship right now. Is there a specific time or situation that made you feel that distance was growing?

### f2. She hasn't replied to my messages in days.

- mode: companion
- draft 1 (fail: fresh_opener): It sounds like that lack of response is making you feel anxious and maybe a bit lonely. Have you ever thought about asking her if everything is okay?
- draft 2 (fail: no_advice): It feels like waiting for a reply can make you feel anxious or like something is wrong. Have you thought about what might be going on for her lately?
- final (generated): It sounds like that lack of response is making you feel anxious and maybe a bit lonely. Have you ever thought about asking her if everything is okay?

### f3. I saw she posted photos with other friends.

- mode: companion
- draft 1 (pass): It feels like seeing her with others makes you feel left out or jealous. Have you ever tried talking to her about how you felt without making it a big fight?
- final (generated): It feels like seeing her with others makes you feel left out or jealous. Have you ever tried talking to her about how you felt without making it a big fight?

### f4. Maybe I did something to upset her.

- mode: companion
- draft 1 (fail: fresh_opener): It sounds like you are starting to wonder if your actions caused her to pull away. What do you think might have happened between you two recently?
- draft 2 (fail: fresh_opener): It sounds like you are wondering if your actions might have caused her to pull away. Do you feel like you could reach out to check on her directly without blaming yourself?
- final (generated): It sounds like you are starting to wonder if your actions caused her to pull away. What do you think might have happened between you two recently?

### f5. It's making me sad.

- mode: companion
- draft 1 (fail: fresh_opener): It feels like that sadness is weighing heavy on you right now. Would it help to talk about what specific memories or thoughts are bringing up those feelings?
- draft 2 (fail: fresh_opener): It feels like your heart is heavy with sadness right now. Do you want to tell me more about what is weighing on you today?
- final (generated): It feels like that sadness is weighing heavy on you right now. Would it help to talk about what specific memories or thoughts are bringing up those feelings?

### f6. I miss how things used to be.

- mode: companion
- draft 1 (fail: validate_first): Missing how things used to be can make the present feel very hard. Is there something specific about the past that you are trying to hold onto?
- draft 2 (fail: fresh_opener): It feels like you are longing for a connection that used to feel warm and safe. How much do you think your current relationship matches up to that memory?
- final (generated): Missing how things used to be can make the present feel very hard. Is there something specific about the past that you are trying to hold onto?

## Conversation: good news

### g1. I got into the course I applied for!

- mode: companion
- draft 1 (pass): That is exciting news to hear, and it sounds like a wonderful achievement for you. How does it feel to know you have taken that next step?
- final (generated): That is exciting news to hear, and it sounds like a wonderful achievement for you. How does it feel to know you have taken that next step?

### g2. I'm excited but also nervous.

- mode: companion
- draft 1 (pass): It is completely normal to feel both excitement and nervousness when you are stepping into something new. What is the one thing that worries you the most about starting this course?
- final (generated): It is completely normal to feel both excitement and nervousness when you are stepping into something new. What is the one thing that worries you the most about starting this course?

### g3. It means moving to a new city.

- mode: companion
- draft 1 (pass): Moving to a new city can feel overwhelming because it involves leaving your familiar surroundings and facing many unknowns. How do you think your friends and family are feeling about your decision to move?
- final (generated): Moving to a new city can feel overwhelming because it involves leaving your familiar surroundings and facing many unknowns. How do you think your friends and family are feeling about your decision to move?

### g4. I won't know anyone there.

- mode: companion
- draft 1 (pass): Not knowing anyone in a new place can feel scary and lonely. Do you feel ready to face that uncertainty, or does it feel too heavy right now?
- final (generated): Not knowing anyone in a new place can feel scary and lonely. Do you feel ready to face that uncertainty, or does it feel too heavy right now?

### g5. My family is really proud though.

- mode: companion
- draft 1 (fail: validate_first): Hearing that your family is proud makes it easier to carry the weight of this big change. What does their support mean to you as you prepare for this next chapter?
- draft 2 (fail: validate_first): It is wonderful that your family feels so proud of you, even when the fear of being alone is present. Does their support make the feeling of not knowing anyone a little less scary for you?
- final (generated): Hearing that your family is proud makes it easier to carry the weight of this big change. What does their support mean to you as you prepare for this next chapter?

### g6. I guess I'm still processing it all.

- mode: companion
- draft 1 (pass): It makes sense to feel like you are still sorting through all the big emotions and details. What is one thing you are hoping to figure out before you leave?
- final (generated): It makes sense to feel like you are still sorting through all the big emotions and details. What is one thing you are hoping to figure out before you leave?

